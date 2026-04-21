"""Iteration-trace endpoints.

Returns a compact HTML partial listing recent role-execution traces for a
project. The UI embeds it under the knowledge panel; M0 shows single-
iteration rows (NullEvaluator), later milestones will show multi-iteration
turns produced by real evaluators.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.llm.trace_store import (
    deserialize_actor_output,
    get_traces_for_project,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/projects/{project_id}/traces", response_class=HTMLResponse)
async def list_traces(
    project_id: str,
    request: Request,
    role: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_traces_for_project(db, project_id, role=role, limit=limit)

    traces = []
    for row in rows:
        output = deserialize_actor_output(row.actor_output)
        traces.append({
            "id": row.id,
            "role": row.role,
            "iteration": row.iteration,
            "final": row.final,
            "score": row.evaluator_score,
            "critique": row.evaluator_critique,
            "rubric_version": row.rubric_version,
            "created_at": row.created_at,
            "text_preview": (output.get("text") or "").strip()[:160],
            "tool_count": len(output.get("tool_calls") or []),
        })

    return templates.TemplateResponse(
        "partials/iteration_trace.html",
        {"request": request, "project_id": project_id, "traces": traces, "role_filter": role},
    )
