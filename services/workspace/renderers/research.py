"""Feature research renderer — writes specs/NNN-slug/research.md from clarifications."""
from __future__ import annotations

from pathlib import Path

from roles.ba_clarifications import CATALOG_BY_ID


def render_research(ws, feature, clarifications) -> Path:
    lines = [
        f"# Research: {feature.title}",
        "",
        f"**Feature:** {feature.ordinal:03d}-{feature.slug}",
        "",
        "Raw BA clarification answers captured during discovery.",
        "",
    ]

    if clarifications:
        for item in clarifications:
            point = CATALOG_BY_ID.get(item.point_id)
            label = point.name if point else item.point_id
            prompt = point.question_to_user if point else item.point_id
            lines += [
                f"## {label}",
                "",
                f"**Point ID:** `{item.point_id}`",
                f"**Status:** {item.status}",
                "",
                f"**Question**: {prompt}",
                "",
                item.answer or "> *No answer captured.*",
                "",
            ]
    else:
        lines += [
            "> No feature-scoped clarifications captured yet.",
            "",
        ]

    path = ws.feature_research_file(feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
