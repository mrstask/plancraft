"""Feature tasks renderer — writes specs/NNN-slug/tasks.md from feature-scoped tasks."""
from __future__ import annotations

from pathlib import Path


def render_feature_tasks(ws, feature, tasks) -> Path:
    lines = [
        f"# Feature Tasks: {feature.title}",
        "",
        f"## Tasks ({len(tasks)})",
        "",
    ]
    if tasks:
        for task in tasks:
            lines.append(f"- [ ] **{task.title}** ({task.complexity or 'medium'})")
            lines.append(f"  {task.description}")
    else:
        lines.append("> No feature-scoped tasks yet.")
    lines.append("")

    path = ws.feature_file(feature, "tasks.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
