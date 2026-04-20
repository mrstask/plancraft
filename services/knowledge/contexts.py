"""Prompt-context builders for LLM phases.

Each method first tries to read the pre-rendered role-context file from the workspace.
If the file doesn't exist yet (e.g., first turn for a new project) it falls back to
rebuilding the context from DB — same as the original behaviour.
"""
from __future__ import annotations
import logging

from .common import KnowledgeBase
from .queries import ArtifactQueries

log = logging.getLogger(__name__)


def _read_role_file(project_id: str, role: str, db) -> str | None:
    """Try to read a pre-rendered role context file. Returns None on any failure."""
    try:
        from services.knowledge.common import KnowledgeBase as _KB  # avoid circular at module level
        # We need the project's root_path. Use a cached lookup via the common base.
        # Because this is sync we read from the DB session cache if available.
        from sqlalchemy import select as _select
        from models.db import Project as _Project  # noqa: PLC0415
        # Access the sync session state — SQLAlchemy's identity map holds the project
        # if it was loaded in this session; if not, return None and let DB fallback run.
        for obj in db.identity_map.values():  # type: ignore[attr-defined]
            if isinstance(obj, _Project) and obj.id == project_id and obj.root_path:
                from pathlib import Path
                from services.workspace.workspace import ProjectWorkspace
                ws = ProjectWorkspace.from_path(obj.root_path)
                ctx_file = ws.role_context_file(role)
                if ctx_file.exists():
                    return ctx_file.read_text(encoding="utf-8")
                return None
    except Exception:
        log.debug("Role context file lookup failed for %s/%s", project_id, role, exc_info=True)
    return None


class PromptContextBuilder(KnowledgeBase):
    def __init__(self, db):
        super().__init__(db)
        self.queries = ArtifactQueries(db)

    async def get_pm_context(self, project_id: str) -> str:
        """Context for PM phase with full story IDs for prioritization and MVP selection."""
        cached = _read_role_file(project_id, "pm", self.db)
        if cached is not None:
            return cached
        project = await self.get_project(project_id)
        stories = await self.queries.get_all_stories(project_id)
        epics = await self.queries.get_all_epics(project_id)

        lines = [
            f"Project: {project.name}",
            f"Problem: {project.description or '(none)'}",
            "",
            f"## STORIES ({len(stories)}) — use these FULL IDs in update_user_story() and set_mvp_scope()",
        ]

        for story in stories:
            lines.append(f"  [{story.id}] As a {story.as_a}, I want {story.i_want}, so that {story.so_that}")
            lines.append(f"    Priority: {story.priority}")
            if story.epic_id:
                lines.append(f"    Epic ID: {story.epic_id}")
            for ac in (story.acceptance_criteria or []):
                lines.append(f"    AC: {ac.criterion}")

        if epics:
            lines.append(f"\n## EPICS ({len(epics)})")
            for epic in epics:
                lines.append(f"  [{epic.id}] {epic.title}: {epic.description or '(no description)'}")
        else:
            lines.append("\n## EPICS — none recorded yet")

        if project.mvp_story_ids:
            lines.append("\n## CURRENT MVP SCOPE")
            for story_id in project.mvp_story_ids:
                lines.append(f"  - {story_id}")
            if project.mvp_rationale:
                lines.append(f"Rationale: {project.mvp_rationale}")

        return "\n".join(lines)

    async def get_tdd_context(self, project_id: str) -> str:
        """Full context for the TDD phase: stories + components + existing specs/tasks."""
        cached = _read_role_file(project_id, "tdd", self.db)
        if cached is not None:
            return cached
        project = await self.get_project(project_id)
        stories = await self.queries.get_all_stories(project_id)
        components = await self.queries.get_all_components(project_id)
        specs = await self.queries.get_all_test_specs(project_id)
        tasks = await self.queries.get_all_tasks(project_id)

        lines = [
            f"Project: {project.name}",
            f"Problem: {project.description or '(none)'}",
            "",
        ]

        if project.mvp_story_ids:
            lines.append(
                f"MVP scope: {len(project.mvp_story_ids)} stor"
                f"{'y' if len(project.mvp_story_ids) == 1 else 'ies'} selected"
            )
            if project.mvp_rationale:
                lines.append(f"MVP rationale: {project.mvp_rationale}")
            lines.append("")

        lines.append(f"## USER STORIES ({len(stories)}) — use these FULL IDs in story_id / story_ids fields")
        for s in stories:
            lines.append(f"  [{s.id}]  As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
            lines.append(f"    Priority: {s.priority}")
            for ac in (s.acceptance_criteria or []):
                lines.append(f"    AC: {ac.criterion}")

        lines.append(f"\n## COMPONENTS ({len(components)}) — use these FULL IDs in component_id field")
        for c in components:
            lines.append(f"  [{c.id}]  {c.name} ({c.component_type or 'module'}): {c.responsibility}")

        if specs:
            lines.append(f"\n## TEST SPECS ALREADY SAVED ({len(specs)}) — do NOT duplicate these")
            for sp in specs:
                lines.append(f"  [{sp.id}]  {sp.description} [{sp.test_type}]")
        else:
            lines.append("\n## TEST SPECS — none saved yet; you must create all of them now")

        if tasks:
            lines.append(f"\n## TASKS ALREADY PROPOSED ({len(tasks)}) — do NOT duplicate these")
            for t in tasks:
                lines.append(f"  [{t.id}]  {t.title} [{t.complexity}]")
        else:
            lines.append("\n## TASKS — none proposed yet; you must propose all implementation tasks now")

        return "\n".join(lines)

    async def get_full_review_context(self, project_id: str) -> str:
        """Return a formatted string of all artifacts with IDs for the reviewer LLM."""
        cached = _read_role_file(project_id, "review", self.db)
        if cached is not None:
            return cached
        project = await self.get_project(project_id)
        stories = await self.queries.get_all_stories(project_id)
        components = await self.queries.get_all_components(project_id)
        decisions = await self.queries.get_all_decisions(project_id)
        specs = await self.queries.get_all_test_specs(project_id)
        tasks = await self.queries.get_all_tasks(project_id)

        lines = [
            f"Project: {project.name}",
            f"Problem: {project.description or '(none)'}",
            "",
            "=" * 60,
            "ALL ARTIFACTS — review every category for duplicates and quality",
            "=" * 60,
        ]

        lines += [f"\n### STORIES ({len(stories)})"]
        for s in stories:
            lines.append(f"  [{s.id}]")
            lines.append(f"    As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
            lines.append(f"    Priority: {s.priority}")
            if s.acceptance_criteria:
                for ac in s.acceptance_criteria:
                    lines.append(f"    AC: {ac.criterion}")

        lines += [f"\n### COMPONENTS ({len(components)})"]
        for c in components:
            lines.append(f"  [{c.id}]")
            lines.append(f"    Name: {c.name}")
            lines.append(f"    Type: {c.component_type or '–'}")
            lines.append(f"    Responsibility: {c.responsibility}")

        lines += [f"\n### ARCHITECTURE DECISIONS ({len(decisions)})"]
        for d in decisions:
            lines.append(f"  [{d.id}]")
            lines.append(f"    Title: {d.title}")
            lines.append(f"    Decision: {d.decision}")
            if d.context:
                lines.append(f"    Context: {d.context}")

        lines += [f"\n### TEST SPECS ({len(specs)})"]
        for sp in specs:
            lines.append(f"  [{sp.id}]")
            lines.append(f"    Description: {sp.description}")
            lines.append(f"    Type: {sp.test_type}")
            lines.append(f"    Given: {sp.given_context or '–'}")
            lines.append(f"    When: {sp.when_action or '–'}")
            lines.append(f"    Then: {sp.then_expectation or '–'}")

        lines += [f"\n### TASKS ({len(tasks)})"]
        for t in tasks:
            lines.append(f"  [{t.id}]")
            lines.append(f"    Title: {t.title}")
            lines.append(f"    Complexity: {t.complexity}")
            lines.append(f"    Description: {t.description}")

        return "\n".join(lines)
