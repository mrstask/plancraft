"""Feature spec renderer — writes specs/NNN-slug/spec.md from feature-scoped stories."""
from __future__ import annotations

from pathlib import Path


def render_feature_spec(ws, feature, stories) -> Path:
    lines = [
        f"# Feature Spec: {feature.title}",
        "",
        f"**Feature:** {feature.ordinal:03d}-{feature.slug}",
        f"**Status:** {feature.status}",
        "",
        "## Summary",
        "",
        feature.description or "No description yet.",
        "",
        f"## User Stories ({len(stories)})",
        "",
    ]
    if stories:
        for story in stories:
            lines.append(f"### [{story.id}] As a {story.as_a}, I want {story.i_want}")
            lines.append("")
            lines.append(f"So that {story.so_that}.")
            lines.append("")
            if story.acceptance_criteria:
                lines.append("Acceptance criteria:")
                for ac in story.acceptance_criteria:
                    lines.append(f"- [ ] {ac.criterion}")
                lines.append("")
    else:
        lines.append("> No feature-scoped stories yet.")
        lines.append("")

    path = ws.feature_file(feature, "spec.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
