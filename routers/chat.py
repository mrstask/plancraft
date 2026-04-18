"""Chat routes — SSE streaming endpoint + phase-status JSON."""
import json
import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, AsyncSessionLocal
from models.db import Message
from models.domain import compute_phase_status
from services.llm import stream_response
from services.knowledge import KnowledgeService
from services.suggestions import get_suggestions
from services.review_orchestrator import run_full_review

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _sse(event: str, data: dict) -> str:
    """Format a single SSE block as a plain string with \n line endings."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/projects/{project_id}/chat")
async def send_message(
    project_id: str,
    request: Request,
    content: str = Form(...),
    role_tab: str = Form(default="ba"),
    db: AsyncSession = Depends(get_db),
):
    # Persist user message tagged to this phase tab
    user_msg = Message(project_id=project_id, role="user", content=content, role_tab=role_tab)
    db.add(user_msg)
    await db.commit()

    # Build message history for this tab only (each tab has its own context)
    result = await db.execute(
        select(Message)
        .where(Message.project_id == project_id, Message.role_tab == role_tab)
        .order_by(Message.created_at.asc())
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]
    history = history[-settings.max_history_messages:]

    async def event_generator():
        async with AsyncSessionLocal() as stream_db:
            assistant_text: list[str] = []
            active_persona = role_tab

            try:
                async for chunk in stream_response(project_id, history, stream_db, role_tab=role_tab):
                    if chunk["type"] == "thinking":
                        yield _sse("thinking", {"content": chunk["content"]})

                    elif chunk["type"] == "text":
                        assistant_text.append(chunk["content"])
                        yield _sse("token", {"content": chunk["content"]})

                    elif chunk["type"] == "tool_used":
                        yield _sse("tool_used", {"tool": chunk["name"], "result": chunk["result"]})

                    elif chunk["type"] == "done":
                        active_persona = chunk.get("persona", role_tab)

                # Persist assistant message tagged to this tab
                full_text = "".join(assistant_text)
                if full_text:
                    stream_db.add(Message(
                        project_id=project_id,
                        role="assistant",
                        content=full_text,
                        active_persona=active_persona,
                        role_tab=role_tab,
                    ))
                    await stream_db.commit()

                # Fresh snapshot (tool calls may have updated it this turn)
                svc = KnowledgeService(stream_db)
                snapshot = await svc.get_snapshot(project_id)
                suggestions = get_suggestions(active_persona, snapshot)
                phases = [p.to_dict() for p in compute_phase_status(snapshot)]

                yield _sse("done", {
                    "persona": active_persona,
                    "suggestions": suggestions,
                    "phases": phases,
                })

            except Exception as e:
                log.error(f"Stream error: {e}", exc_info=True)
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if behind a proxy
        },
    )


@router.post("/projects/{project_id}/review/full")
async def full_review(project_id: str):
    """
    Multi-pass review SSE stream.
    Runs 5 focused category passes then 1 holistic pass.
    Emits: review_progress, tool_used, done events.
    """
    async def event_generator():
        async with AsyncSessionLocal() as stream_db:
            try:
                async for event in run_full_review(project_id, stream_db):
                    if event["type"] in ("review_progress", "tool_used"):
                        yield _sse(event["type"], event)

                # Final snapshot for phase/panel refresh
                svc = KnowledgeService(stream_db)
                snapshot = await svc.get_snapshot(project_id)
                phases = [p.to_dict() for p in compute_phase_status(snapshot)]
                yield _sse("done", {"persona": "review", "suggestions": [], "phases": phases})

            except Exception as e:
                log.error(f"Full review error: {e}", exc_info=True)
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/projects/{project_id}/knowledge-panel", response_class=HTMLResponse)
async def knowledge_panel(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    snapshot = await svc.get_snapshot(project_id)
    phases = compute_phase_status(snapshot)
    return templates.TemplateResponse(
        "partials/knowledge_panel.html",
        {"request": request, "snapshot": snapshot, "project_id": project_id, "phases": phases},
    )


@router.get("/projects/{project_id}/phase-status")
async def phase_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Lightweight JSON endpoint — called by JS after tool_used events to update the stepper."""
    svc = KnowledgeService(db)
    snapshot = await svc.get_snapshot(project_id)
    return JSONResponse([p.to_dict() for p in compute_phase_status(snapshot)])
