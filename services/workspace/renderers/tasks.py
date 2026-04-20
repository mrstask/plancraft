"""Task renderer — writes tasks.json DAG and one Markdown file per task."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.export.queries import TaskExportData
    from services.workspace.workspace import ProjectWorkspace


def render_tasks_json(ws: "ProjectWorkspace", data: "TaskExportData") -> Path:
    by_complexity: dict[str, int] = {"trivial": 0, "small": 0, "medium": 0, "large": 0}
    task_list: list[dict[str, Any]] = []
    for task in data.tasks:
        complexity = task.complexity or "medium"
        by_complexity[complexity] = by_complexity.get(complexity, 0) + 1
        task_list.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "complexity": complexity,
            "status": "backlog",
            "acceptance_criteria": task.acceptance_criteria or [],
            "file_paths": task.file_paths or [],
            "depends_on": data.deps_by_task.get(task.id, []),
            "story_ids": data.stories_by_task.get(task.id, []),
            "test_spec_ids": data.specs_by_task.get(task.id, []),
        })

    payload = {
        "project": data.project_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tasks": task_list,
        "summary": {"total": len(task_list), "by_complexity": by_complexity},
    }
    path = ws.tasks_json
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def render_task_file(ws: "ProjectWorkspace", n: int, task, data: "TaskExportData") -> Path:
    dep_ids = data.deps_by_task.get(task.id, [])
    story_ids = data.stories_by_task.get(task.id, [])
    spec_ids = data.specs_by_task.get(task.id, [])

    lines = [
        f"# TASK-{n:03d}: {task.title}",
        "",
        f"**Complexity:** {task.complexity or 'medium'}",
        f"**Status:** {task.status or 'pending'}",
        "",
        "## Description",
        "",
        task.description,
        "",
    ]
    if task.acceptance_criteria:
        lines += ["## Acceptance Criteria", ""]
        for ac in task.acceptance_criteria:
            lines.append(f"- [ ] {ac}")
        lines.append("")
    if task.file_paths:
        lines += ["## File Paths", ""]
        for fp in task.file_paths:
            lines.append(f"- `{fp}`")
        lines.append("")
    if dep_ids:
        lines += ["## Dependencies", ""]
        for dep in dep_ids:
            lines.append(f"- {dep}")
        lines.append("")
    if story_ids:
        lines += ["## Related Stories", ""]
        for sid in story_ids:
            lines.append(f"- [{sid}](../docs/stories/)")
        lines.append("")
    if spec_ids:
        lines += ["## Test Specs", ""]
        for spid in spec_ids:
            lines.append(f"- [{spid}](../tests/specs/)")
        lines.append("")

    path = ws.task_file(n)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_all(ws: "ProjectWorkspace", data: "TaskExportData") -> list[Path]:
    paths = [render_tasks_json(ws, data)]
    for n, task in enumerate(data.tasks, start=1):
        paths.append(render_task_file(ws, n, task, data))
    return paths
