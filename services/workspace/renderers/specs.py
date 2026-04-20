"""Test spec renderer — writes one Markdown file per test specification."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import TestSpec
    from services.workspace.workspace import ProjectWorkspace


def render_spec(ws: "ProjectWorkspace", n: int, spec: "TestSpec") -> Path:
    lines = [
        f"# SPEC-{n:03d}: {spec.description}",
        "",
        f"**Type:** {spec.test_type or 'unit'}",
        "",
        "## Scenario",
        "",
    ]
    if spec.given_context:
        lines += [f"**Given:** {spec.given_context}", ""]
    if spec.when_action:
        lines += [f"**When:** {spec.when_action}", ""]
    if spec.then_expectation:
        lines += [f"**Then:** {spec.then_expectation}", ""]

    path = ws.spec_file(n)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_all(ws: "ProjectWorkspace", specs: list["TestSpec"]) -> list[Path]:
    return [render_spec(ws, n, sp) for n, sp in enumerate(specs, start=1)]
