"""Workspace renderer orchestrator.

Loads all project data from DB and writes the full docs-as-code workspace.
Called as a fire-and-forget background task after each LLM turn that modifies artifacts.
All operations are idempotent — safe to re-run at any time.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from services.export.queries import ExportDataLoader
from services.workspace.workspace import ProjectWorkspace
from services.workspace.renderers import arc42, adr, stories, specs, tasks, c4, readme
from services.workspace import role_context as rc

log = logging.getLogger(__name__)


async def render_workspace(project_id: str, db: AsyncSession) -> None:
    """Render all workspace files for a project. Safe to call in the background."""
    try:
        loader = ExportDataLoader(db)
        project = await loader.get_project(project_id)

        if not project.root_path:
            log.debug("Project %s has no workspace path — skipping render", project_id)
            return

        ws = ProjectWorkspace.from_path(project.root_path)
        ws.scaffold()  # ensure dirs exist if workspace was created before this feature

        arc42_data = await loader.load_arc42_export(project_id)
        task_data = await loader.load_task_export(project_id)

        # arc42 sections
        arc42.render_all(ws, arc42_data)

        # per-artifact files
        adr.render_all(ws, list(arc42_data.decisions))
        stories.render_all(ws, list(arc42_data.stories))
        specs.render_all(ws, list(arc42_data.specs))
        tasks.render_all(ws, task_data)

        # C4 model
        c4.render_c4(ws, arc42_data.project_name, list(arc42_data.components))

        # README index
        readme.render_readme(ws, arc42_data)

        # Per-role context files for LLM prompt building
        await rc.render_all_roles(ws, project_id, db)

        log.info("Workspace rendered for project %s → %s", project_id, ws.root)

    except Exception:
        log.exception("Workspace render failed for project %s", project_id)


def schedule_render(project_id: str, db: AsyncSession) -> None:
    """Schedule a background render without blocking the caller."""
    asyncio.ensure_future(render_workspace(project_id, db))
