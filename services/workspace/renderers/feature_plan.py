"""Feature plan renderer — writes specs/NNN-slug/plan.md from components and decisions."""
from __future__ import annotations

from pathlib import Path


def render_feature_plan(ws, feature, components, decisions) -> Path:
    lines = [
        f"# Feature Plan: {feature.title}",
        "",
        "## Scope",
        "",
        feature.description or "No description yet.",
        "",
        f"## Components in Context ({len(components)})",
        "",
    ]
    if components:
        for component in components:
            lines.append(f"- **{component.name}** ({component.component_type or 'module'}): {component.responsibility}")
    else:
        lines.append("> No components recorded yet.")
    lines.append("")
    lines.append(f"## Decisions ({len(decisions)})")
    lines.append("")
    if decisions:
        for decision in decisions:
            lines.append(f"- **{decision.title}**: {decision.decision}")
    else:
        lines.append("> No feature-specific decisions recorded yet.")
    lines.append("")

    path = ws.feature_file(feature, "plan.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
