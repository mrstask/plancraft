"""Tech stack renderer — writes product/tech-stack.md from founder artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import TechStackEntry
    from services.workspace.workspace import ProjectWorkspace


def render_tech_stack(ws: "ProjectWorkspace", entries: list["TechStackEntry"]) -> Path:
    lines = [
        "# Tech Stack",
        "",
    ]
    if not entries:
        lines += ["> *No tech stack entries recorded yet.*", ""]
    else:
        for entry in entries:
            lines += [
                f"## {entry.layer or 'Layer'}",
                "",
                f"**Choice:** {entry.choice or 'Not yet defined'}",
                "",
                entry.rationale or "> *No rationale yet.*",
                "",
            ]
    path = ws.tech_stack_file
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
