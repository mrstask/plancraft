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
from models.domain import compute_feature_phase_status, compute_phase_status
from services.llm import build_actor_output, record_single_turn, stream_response
from services.llm.evaluators import get_evaluator
from services.knowledge import KnowledgeService
from services.suggestions import get_suggestions
from services.review_orchestrator import run_full_review
from services.workspace.renderer import schedule_render

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
    role_tab: str = Form(default="founder"),
    feature_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Persist user message tagged to this phase tab
    user_msg = Message(project_id=project_id, role="user", content=content, role_tab=role_tab, feature_id=feature_id)
    db.add(user_msg)
    await db.commit()

    # Build message history for this tab only (each tab has its own context)
    history_stmt = (
        select(Message)
        .where(Message.project_id == project_id, Message.role_tab == role_tab)
        .order_by(Message.created_at.asc())
    )
    if feature_id is None:
        history_stmt = history_stmt.where(Message.feature_id.is_(None))
    else:
        history_stmt = history_stmt.where(Message.feature_id == feature_id)
    result = await db.execute(history_stmt)
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]
    history = history[-settings.max_history_messages:]

    async def event_generator():
        async with AsyncSessionLocal() as stream_db:
            assistant_text: list[str] = []
            tool_calls_made: list[dict] = []
            active_persona = role_tab

            try:
                async for chunk in stream_response(project_id, history, stream_db, role_tab=role_tab, feature_id=feature_id):
                    if chunk["type"] == "thinking":
                        yield _sse("thinking", {"content": chunk["content"]})

                    elif chunk["type"] == "text":
                        assistant_text.append(chunk["content"])
                        yield _sse("token", {"content": chunk["content"]})

                    elif chunk["type"] == "tool_used":
                        tool_calls_made.append({"name": chunk["name"], "result": chunk["result"]})
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
                        feature_id=feature_id,
                    ))
                    await stream_db.commit()

                # M0: record a single iteration trace for this role turn. With
                # NullEvaluator (default) the loop does not retry; real
                # evaluators in later milestones may cause re-runs.
                try:
                    actor_output = build_actor_output(
                        text=full_text,
                        tool_calls=tool_calls_made,
                    )
                    await record_single_turn(
                        stream_db,
                        project_id=project_id,
                        feature_id=feature_id,
                        role=role_tab,
                        actor_prompt=content,
                        actor_output=actor_output,
                        evaluator=get_evaluator(role_tab),
                    )
                except Exception as trace_exc:
                    log.warning("Trace persistence failed: %s", trace_exc)

                # Fresh snapshot (tool calls may have updated it this turn)
                svc = KnowledgeService(stream_db, feature_id=feature_id)
                snapshot = await svc.get_snapshot(project_id)
                suggestions = get_suggestions(active_persona, snapshot)
                phases = [p.to_dict() for p in (compute_feature_phase_status(snapshot) if feature_id else compute_phase_status(snapshot))]

                # Render workspace files in background (idempotent, non-blocking)
                schedule_render(project_id, stream_db)

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
            review_tool_calls: list[dict] = []
            try:
                async for event in run_full_review(project_id, stream_db):
                    if event["type"] in ("review_progress", "tool_used"):
                        if event["type"] == "tool_used":
                            review_tool_calls.append({
                                "name": event.get("name") or event.get("tool"),
                                "result": event.get("result"),
                            })
                        yield _sse(event["type"], event)

                # Record one trace row for the full-review turn (M1).
                # Pass constitution_md so ReviewerEvaluator can check rules.
                try:
                    actor_output = build_actor_output(
                        text="",
                        tool_calls=review_tool_calls,
                    )
                    svc_ctx = KnowledgeService(stream_db)
                    _project = await svc_ctx._get_project(project_id)
                    await record_single_turn(
                        stream_db,
                        project_id=project_id,
                        role="review",
                        actor_prompt="run_full_review",
                        actor_output=actor_output,
                        evaluator=get_evaluator("review"),
                        context={"constitution_md": _project.constitution_md or ""},
                    )
                except Exception as trace_exc:
                    log.warning("Full-review trace persistence failed: %s", trace_exc)

                # Final snapshot for phase/panel refresh
                svc = KnowledgeService(stream_db)
                snapshot = await svc.get_snapshot(project_id)
                phases = [p.to_dict() for p in compute_phase_status(snapshot)]
                schedule_render(project_id, stream_db)
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
    feature_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db, feature_id=feature_id)
    snapshot = await svc.get_snapshot(project_id)
    phases = compute_feature_phase_status(snapshot) if feature_id else compute_phase_status(snapshot)
    return templates.TemplateResponse(
        "partials/knowledge_panel.html",
        {"request": request, "snapshot": snapshot, "project_id": project_id, "feature_id": feature_id, "phases": phases},
    )


@router.get("/projects/{project_id}/phase-status")
async def phase_status(
    project_id: str,
    feature_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lightweight JSON endpoint — called by JS after tool_used events to update the stepper."""
    svc = KnowledgeService(db, feature_id=feature_id)
    snapshot = await svc.get_snapshot(project_id)
    phases = compute_feature_phase_status(snapshot) if feature_id else compute_phase_status(snapshot)
    return JSONResponse([p.to_dict() for p in phases])
