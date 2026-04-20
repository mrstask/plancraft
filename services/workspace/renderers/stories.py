"""User story renderer — writes one Markdown file per user story."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import UserStory
    from services.workspace.workspace import ProjectWorkspace


def render_story(ws: "ProjectWorkspace", n: int, story: "UserStory") -> Path:
    ac_lines: list[str] = []
    for ac in (story.acceptance_criteria or []):
        ac_lines.append(f"- [ ] {ac.criterion}")

    lines = [
        f"# US-{n:03d}",
        "",
        f"**Priority:** {story.priority or 'should'}",
        f"**Status:** {story.status or 'draft'}",
        "",
        "## Story",
        "",
        f"As a **{story.as_a}**,",
        f"I want **{story.i_want}**,",
        f"so that **{story.so_that}**.",
        "",
    ]
    if ac_lines:
        lines += ["## Acceptance Criteria", ""]
        lines += ac_lines
        lines.append("")

    path = ws.story_file(n)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_all(ws: "ProjectWorkspace", stories: list["UserStory"]) -> list[Path]:
    return [render_story(ws, n, s) for n, s in enumerate(stories, start=1)]
