"""Write-side commands for reusable profiles."""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import func, select

from models.db import ArchitectureDecision, Profile, Project, TechStackEntry
from services.profiles.queries import ProfileQueries
from services.profiles.renderer import (
    build_profile_ref,
    delete_profile_mirror,
    parse_conventions_json,
    parse_tech_stack_template,
    render_profile_mirror,
    serialize_conventions,
    serialize_tech_stack_template,
)


class ProfileCommands:
    def __init__(self, db):
        self.db = db
        self.queries = ProfileQueries(db)

    async def ensure_starter_profiles(self) -> list[Profile]:
        result = await self.db.execute(select(func.count(Profile.id)))
        if (result.scalar_one() or 0) > 0:
            return await self.queries.list_profiles()

        from config import settings

        settings.profiles_root.mkdir(parents=True, exist_ok=True)
        if any(settings.profiles_root.iterdir()):
            return []

        starter_dir = Path(__file__).resolve().parent.parent / "workspace" / "templates" / "starter_profiles"
        created: list[Profile] = []
        for template_path in sorted(starter_dir.glob("*.yml")):
            payload = json.loads(template_path.read_text(encoding="utf-8"))
            created.append(
                await self.create_profile(
                    name=str(payload.get("name", template_path.stem)).strip(),
                    description=str(payload.get("description", "")).strip(),
                    version=str(payload.get("version", "1.0.0")).strip() or "1.0.0",
                    constitution_md=str(payload.get("constitution_md", "")).strip(),
                    tech_stack_entries=list(payload.get("tech_stack_template", []) or []),
                    conventions=dict(payload.get("conventions", {}) or {}),
                )
            )
        return created

    async def create_profile(
        self,
        *,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        constitution_md: str = "",
        tech_stack_entries: list[dict[str, str]] | None = None,
        conventions: dict | None = None,
    ) -> Profile:
        existing = await self.queries.get_profile_by_name(name)
        if existing:
            raise ValueError(f"Profile '{name}' already exists.")

        profile = Profile(
            name=name.strip(),
            description=description.strip(),
            version=version.strip() or "1.0.0",
            constitution_md=constitution_md,
            tech_stack_template=serialize_tech_stack_template(list(tech_stack_entries or [])),
            conventions_json=serialize_conventions(dict(conventions or {})),
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        render_profile_mirror(profile)
        return profile

    async def update_profile(
        self,
        profile_id: str,
        *,
        name: str,
        description: str,
        version: str,
        constitution_md: str,
        tech_stack_entries: list[dict[str, str]] | None,
        conventions: dict | None,
    ) -> Profile:
        profile = await self.queries.get_profile(profile_id)
        if not profile:
            raise ValueError("Profile not found.")

        old_name = profile.name
        if profile.name != name.strip():
            conflict = await self.queries.get_profile_by_name(name.strip())
            if conflict and conflict.id != profile.id:
                raise ValueError(f"Profile '{name}' already exists.")

        profile.name = name.strip()
        profile.description = description.strip()
        profile.version = version.strip() or "1.0.0"
        profile.constitution_md = constitution_md
        profile.tech_stack_template = serialize_tech_stack_template(list(tech_stack_entries or []))
        profile.conventions_json = serialize_conventions(dict(conventions or {}))

        await self.db.commit()
        await self.db.refresh(profile)
        if old_name != profile.name:
            delete_profile_mirror(old_name)
        render_profile_mirror(profile)
        return profile

    async def delete_profile(self, profile_id: str) -> None:
        profile = await self.queries.get_profile(profile_id)
        if not profile:
            return
        profile_name = profile.name
        await self.db.delete(profile)
        await self.db.commit()
        delete_profile_mirror(profile_name)

    async def duplicate_profile(self, profile_id: str, *, new_name: str | None = None) -> Profile:
        source = await self.queries.get_profile(profile_id)
        if not source:
            raise ValueError("Profile not found.")

        base_name = new_name.strip() if new_name else f"{source.name} Copy"
        candidate = base_name
        suffix = 2
        while await self.queries.get_profile_by_name(candidate):
            candidate = f"{base_name} {suffix}"
            suffix += 1

        return await self.create_profile(
            name=candidate,
            description=source.description,
            version=source.version,
            constitution_md=source.constitution_md,
            tech_stack_entries=parse_tech_stack_template(source.tech_stack_template),
            conventions=parse_conventions_json(source.conventions_json),
        )

    async def inherit_profile_into_project(self, project_id: str, profile_id: str) -> Project:
        project_result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found.")

        profile = await self.queries.get_profile(profile_id)
        if not profile:
            raise ValueError("Profile not found.")

        project.constitution_md = profile.constitution_md
        project.profile_ref = build_profile_ref(profile.name, profile.version)

        existing_entries = await self.db.execute(select(TechStackEntry).where(TechStackEntry.project_id == project_id))
        for entry in existing_entries.scalars().all():
            await self.db.delete(entry)

        for row in parse_tech_stack_template(profile.tech_stack_template):
            self.db.add(
                TechStackEntry(
                    project_id=project_id,
                    layer=row["layer"],
                    choice=row["choice"],
                    rationale=row["rationale"],
                )
            )

        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def save_profile_from_project(
        self,
        project_id: str,
        profile_name: str,
        *,
        description: str = "",
        strip_project_refs: bool = True,
    ) -> Profile:
        project_result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError("Project not found.")

        tech_rows = await self.db.execute(
            select(TechStackEntry).where(TechStackEntry.project_id == project_id).order_by(TechStackEntry.updated_at.asc())
        )
        decisions = await self.db.execute(
            select(ArchitectureDecision)
            .where(ArchitectureDecision.project_id == project_id)
            .order_by(ArchitectureDecision.created_at.desc())
            .limit(5)
        )

        constitution_md = project.constitution_md or ""
        if strip_project_refs:
            constitution_md = self._strip_project_refs(constitution_md, project.name)

        tech_stack_entries = []
        for entry in tech_rows.scalars().all():
            rationale = entry.rationale or ""
            if strip_project_refs:
                rationale = self._strip_project_refs(rationale, project.name)
            tech_stack_entries.append(
                {
                    "layer": entry.layer,
                    "choice": entry.choice,
                    "rationale": rationale,
                }
            )

        conventions = {
            "source": {
                "saved_from_project": project.name,
                "strip_project_refs": strip_project_refs,
            },
            "architecture_decisions": [
                {
                    "title": self._strip_project_refs(decision.title or "", project.name) if strip_project_refs else (decision.title or ""),
                    "decision": self._strip_project_refs(decision.decision or "", project.name) if strip_project_refs else (decision.decision or ""),
                }
                for decision in decisions.scalars().all()
            ],
        }

        return await self.create_profile(
            name=profile_name.strip(),
            description=description.strip(),
            version="1.0.0",
            constitution_md=constitution_md,
            tech_stack_entries=tech_stack_entries,
            conventions=conventions,
        )

    def _strip_project_refs(self, text: str, project_name: str) -> str:
        if not text.strip():
            return text
        project_name = project_name.strip()
        if not project_name:
            return text

        pattern = re.compile(re.escape(project_name), re.IGNORECASE)
        lines = []
        for line in text.splitlines():
            rewritten = pattern.sub("the project", line).strip()
            rewritten = re.sub(r"\s{2,}", " ", rewritten)
            lines.append(rewritten)
        cleaned = "\n".join(lines).strip()
        return cleaned or text
