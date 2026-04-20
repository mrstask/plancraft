"""Export routes — workspace zip, task DAG JSON, and arc42 docs."""
import io
import json
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.export_service import build_task_dag, build_arc42
from services.export.queries import ExportDataLoader
from services.workspace.workspace import ProjectWorkspace
from services.workspace.renderer import render_workspace

router = APIRouter()


@router.get("/projects/{project_id}/export/workspace")
async def export_workspace(project_id: str, db: AsyncSession = Depends(get_db)):
    """Re-render and download the full docs-as-code workspace as a zip archive."""
    loader = ExportDataLoader(db)
    try:
        project = await loader.get_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not project.root_path:
        raise HTTPException(status_code=422, detail="Project workspace not initialised yet.")

    # Ensure workspace is up to date before zipping
    await render_workspace(project_id, db)

    ws = ProjectWorkspace.from_path(project.root_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in ws.root.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(ws.root))

    buf.seek(0)
    safe_name = ws.root.name
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}.zip"},
    )


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
    """Export arc42 architecture documentation as single Markdown file (legacy)."""
    try:
        content = await build_arc42(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=arc42.md"},
    )
