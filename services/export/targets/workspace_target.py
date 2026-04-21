"""Workspace export target — full docs-as-code workspace directory."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BuildResult


class WorkspaceTarget:
    name = "workspace"
    display_name = "Full Workspace"
    description = "Complete docs-as-code workspace: arc42, ADRs, stories, BA artifacts, role context files, constitution."

    async def build(self, project_id: str, out_dir: Path, db: AsyncSession) -> BuildResult:
        from services.export.queries import ExportDataLoader
        from services.workspace.renderer import render_workspace
        from services.workspace.workspace import ProjectWorkspace

        loader = ExportDataLoader(db)
        project = await loader.get_project(project_id)

        if not project.root_path:
            raise ValueError("Project workspace not initialised yet.")

        await render_workspace(project_id, db)

        ws = ProjectWorkspace.from_path(project.root_path)
        result = BuildResult(out_dir=out_dir)

        for src in ws.root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(ws.root)
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            result.add_file(dest)

        return result
