"""Export routes — arc42 docs and task DAG JSON."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.export_service import build_task_dag, build_arc42

router = APIRouter()


@router.get("/projects/{project_id}/export/tasks")
async def export_tasks(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export atomized task DAG as JSON (dev_team compatible)."""
    try:
        payload = await build_task_dag(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    content = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=tasks.json"},
    )


@router.get("/projects/{project_id}/export/arc42")
async def export_arc42(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export arc42 architecture documentation as Markdown."""
    try:
        content = await build_arc42(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=arc42.md"},
    )
