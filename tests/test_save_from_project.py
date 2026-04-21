from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base
from models import db as models_db  # noqa: F401
from models.db import ArchitectureDecision, Project, TechStackEntry
from services.profiles import ProfileCommands, parse_conventions_json, parse_tech_stack_template


class SaveProfileFromProjectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._tmp = tempfile.TemporaryDirectory()
        self._original_profiles_root = settings.profiles_root
        settings.profiles_root = Path(self._tmp.name)

    async def asyncTearDown(self):
        settings.profiles_root = self._original_profiles_root
        self._tmp.cleanup()
        await self.engine.dispose()

    async def test_save_from_project_strips_refs_and_can_seed_another_project(self):
        async with self.session_factory() as session:
            project = Project(
                name="Acme Planner",
                constitution_md=(
                    "# Constitution\n\n"
                    "- Prefer explicit service boundaries.\n"
                    "- Acme Planner should keep internal names out of reusable guidance.\n"
                ),
            )
            session.add(project)
            await session.flush()

            session.add(
                TechStackEntry(
                    project_id=project.id,
                    layer="backend",
                    choice="FastAPI",
                    rationale="Use predictable Python service boundaries.\nAcme Planner should stay easy to extend.",
                )
            )
            session.add(
                ArchitectureDecision(
                    project_id=project.id,
                    title="Acme Planner data boundaries",
                    decision="Keep reusable decision language generic and explicit.",
                )
            )
            await session.commit()
            await session.refresh(project)

            commands = ProfileCommands(session)
            profile = await commands.save_profile_from_project(
                project.id,
                "Reusable SaaS Profile",
                description="Derived from a real planning project.",
                strip_project_refs=True,
            )

            self.assertNotIn("Acme Planner", profile.constitution_md)
            tech_entries = parse_tech_stack_template(profile.tech_stack_template)
            self.assertEqual(len(tech_entries), 1)
            self.assertNotIn("Acme Planner", tech_entries[0]["rationale"])

            conventions = parse_conventions_json(profile.conventions_json)
            decision_titles = [row["title"] for row in conventions.get("architecture_decisions", [])]
            self.assertTrue(decision_titles)
            self.assertFalse(any("Acme Planner" in title for title in decision_titles))

            other_project = Project(name="Second App")
            session.add(other_project)
            await session.commit()
            await session.refresh(other_project)

            await commands.inherit_profile_into_project(other_project.id, profile.id)
            await session.commit()
            await session.refresh(other_project)

            seeded_tech = await session.execute(
                select(TechStackEntry).where(TechStackEntry.project_id == other_project.id)
            )
            self.assertEqual(other_project.constitution_md, profile.constitution_md)
            self.assertEqual(len(seeded_tech.scalars().all()), 1)


if __name__ == "__main__":
    unittest.main()
