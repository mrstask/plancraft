"""ADR renderer that splits feature-local ADRs from cross-cutting ADRs."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _render_decision(path: Path, n: int, decision) -> Path:
    consequences = decision.consequences or {}
    positives = consequences.get("positive") or []
    negatives = consequences.get("negative") or []

    lines = [
        f"# ADR-{n:04d}: {decision.title}",
        "",
        "**Status:** accepted",
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
        lines += [f"- {item}" for item in positives]
        lines.append("")
    if negatives:
        lines += ["## Trade-offs / Risks", ""]
        lines += [f"- {item}" for item in negatives]
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_split_adrs(ws, decisions: Iterable, features_by_id: dict[str, object]) -> list[Path]:
    paths: list[Path] = []
    decisions = list(decisions)
    project_decisions = [decision for decision in decisions if not getattr(decision, "feature_id", None)]
    feature_decisions: dict[str, list] = {}
    for decision in decisions:
        feature_id = getattr(decision, "feature_id", None)
        if feature_id:
            feature_decisions.setdefault(feature_id, []).append(decision)

    for n, decision in enumerate(project_decisions, start=1):
        paths.append(_render_decision(ws.adr_file(n, decision.title), n, decision))

    for feature_id, rows in feature_decisions.items():
        feature = features_by_id.get(feature_id)
        if not feature:
            continue
        for n, decision in enumerate(rows, start=1):
            paths.append(_render_decision(ws.feature_adr_file(feature, n, decision.title), n, decision))

    return paths
