"""Tasks DAG export target — JSON file."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from .base import BuildResult


class TasksTarget:
    name = "tasks"
    display_name = "Task DAG (JSON)"
    description = "Atomized implementation task graph with dependencies, story links, and test spec IDs."

    async def build(self, project_id: str, out_dir: Path, db: AsyncSession) -> BuildResult:
        from services.export_service import build_task_dag
        payload = await build_task_dag(project_id, db)
        out_path = out_dir / "tasks.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        result = BuildResult(out_dir=out_dir)
        result.add_file(out_path)
        return result
