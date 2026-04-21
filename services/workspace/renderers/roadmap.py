"""Roadmap renderer — writes product/roadmap.md from founder artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import ProjectRoadmapItem
    from services.workspace.workspace import ProjectWorkspace


def render_roadmap(ws: "ProjectWorkspace", items: list["ProjectRoadmapItem"]) -> Path:
    lines = [
        "# Roadmap",
        "",
    ]
    if not items:
        lines += ["> *No roadmap items recorded yet.*", ""]
    else:
        for item in items:
            prefix = "MVP" if item.mvp else "Later"
            lines += [
                f"## {item.ordinal}. {item.title or 'Untitled roadmap item'}",
                "",
                f"- Track: {prefix}",
            ]
            if item.linked_epic_id:
                lines.append(f"- Linked epic: `{item.linked_epic_id}`")
            lines += [
                "",
                item.description or "> *No description yet.*",
                "",
            ]
    path = ws.roadmap_file
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
