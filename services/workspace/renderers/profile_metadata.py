"""Profile metadata renderer — writes .plancraft/profile.yml for inherited projects."""
from __future__ import annotations

from typing import TYPE_CHECKING

from services.profiles.renderer import render_project_profile_metadata as _render

if TYPE_CHECKING:
    from services.workspace.workspace import ProjectWorkspace


def render_profile_metadata(ws: "ProjectWorkspace", profile_ref: str | None):
    return _render(ws, profile_ref)
