"""Constitution renderer — writes .plancraft/constitution.md from Project.constitution_md."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.workspace.workspace import ProjectWorkspace


def render_constitution(ws: "ProjectWorkspace", constitution_md: str) -> Path:
    """Write the project constitution to .plancraft/constitution.md."""
    path = ws.constitution_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(constitution_md, encoding="utf-8")
    return path
