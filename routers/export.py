"""Export routes — arc42 docs and task DAG JSON. Stubbed for Phase 4."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

router = APIRouter()


@router.get("/projects/{project_id}/export/tasks")
async def export_tasks(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export atomized task DAG as JSON (dev_team compatible). Phase 4."""
    # TODO: implement services/export/tasks.py
    return JSONResponse({"status": "not_implemented", "phase": 4})


@router.get("/projects/{project_id}/export/arc42")
async def export_arc42(project_id: str, db: AsyncSession = Depends(get_db)):
    """Export arc42 markdown documentation. Phase 4."""
    # TODO: implement services/export/arc42.py
    return JSONResponse({"status": "not_implemented", "phase": 4})
