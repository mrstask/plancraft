"""ADR renderer — writes one Markdown file per architecture decision."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.db import ArchitectureDecision
    from services.workspace.workspace import ProjectWorkspace


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render_adr(ws: "ProjectWorkspace", n: int, decision: "ArchitectureDecision") -> Path:
    consequences = decision.consequences or {}
    positives = consequences.get("positive") or []
    negatives = consequences.get("negative") or []

    lines = [
        f"# ADR-{n:04d}: {decision.title}",
        "",
        f"**Status:** accepted",
        f"**Date:** {decision.created_at.strftime('%Y-%m-%d') if decision.created_at else '–'}",
        "",
        "## Context",
        "",
        decision.context or "> *Not captured.*",
        "",
        "## Decision",
        "",
        decision.decision,
        "",
    ]
    if positives:
        lines += ["## Positive Consequences", ""]
        lines += [f"- {p}" for p in positives]
        lines.append("")
    if negatives:
        lines += ["## Trade-offs / Risks", ""]
        lines += [f"- {item}" for item in negatives]
        lines.append("")

    path = ws.adr_file(n, decision.title)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_all(ws: "ProjectWorkspace", decisions: list["ArchitectureDecision"]) -> list[Path]:
    return [render_adr(ws, n, dec) for n, dec in enumerate(decisions, start=1)]
