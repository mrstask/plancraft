"""Mission renderer — writes product/mission.md from founder artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import ProjectMission
    from services.workspace.workspace import ProjectWorkspace


def render_mission(ws: "ProjectWorkspace", mission: "ProjectMission | None") -> Path:
    lines = [
        "# Mission",
        "",
        "## Statement",
        "",
        (mission.statement if mission and mission.statement else "> *Not yet defined.*"),
        "",
        "## Target Users",
        "",
        (mission.target_users if mission and mission.target_users else "> *Not yet defined.*"),
        "",
        "## Problem",
        "",
        (mission.problem if mission and mission.problem else "> *Not yet defined.*"),
        "",
    ]
    path = ws.mission_file
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
