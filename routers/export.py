"""Export routes — workspace zip, task DAG JSON, arc42 docs, and pluggable targets."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.export.queries import ExportDataLoader
from services.export.targets import TARGETS
from services.export_service import build_arc42, build_ba_bundle, build_export, build_task_dag
from services.workspace.renderer import render_workspace
from services.workspace.workspace import ProjectWorkspace

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


@router.get("/projects/{project_id}/export/ba")
async def export_ba(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export all BA artifacts as a structured JSON bundle."""
    try:
        payload = await build_ba_bundle(project_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    content = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ba_bundle.json"},
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


# ---------------------------------------------------------------------------
# Pluggable target endpoints (M6)
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/export/targets")
async def list_export_targets(project_id: str):
    """List all available export targets with name, display_name, and description."""
    return JSONResponse([
        {"name": t.name, "display_name": t.display_name, "description": t.description}
        for t in TARGETS
    ])


@router.get("/projects/{project_id}/export/download")
async def export_download(
    project_id: str,
    target: str = Query(..., description="Export target name, e.g. 'arc42'"),
    db: AsyncSession = Depends(get_db),
):
    """Build an export for any registered target and return a zip with a validation report."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "export"
            out_dir.mkdir()
            result = await build_export(target, project_id, out_dir, db)

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in result.files_written:
                    zf.write(f, f.relative_to(out_dir))
                # Sidecar validation report
                report = {
                    "target": target,
                    "schema_valid": result.schema_valid,
                    "schema_errors": result.schema_errors,
                    "files": [str(f.relative_to(out_dir)) for f in result.files_written],
                }
                zf.writestr("validation-report.json", json.dumps(report, indent=2))

            buf.seek(0)
            return Response(
                content=buf.read(),
                media_type="application/zip",
                headers={"Content-Disposition": f"attachment; filename={target}-export.zip"},
            )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() or "not initialised" in str(exc).lower() else 400, detail=str(exc))
