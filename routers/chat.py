"""Chat routes — SSE streaming endpoint."""
import json
import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import Message
from services.llm import stream_response
from services.knowledge import KnowledgeService
from services.suggestions import get_suggestions

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
    db: AsyncSession = Depends(get_db),
):
    # Persist user message
    user_msg = Message(project_id=project_id, role="user", content=content)
    db.add(user_msg)
    await db.commit()

    # Build message history
    result = await db.execute(
        select(Message)
        .where(Message.project_id == project_id)
        .order_by(Message.created_at.asc())
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

    async def event_generator():
        assistant_text: list[str] = []
        active_persona = "ba"

        try:
            async for chunk in stream_response(project_id, history, db):
                if chunk["type"] == "thinking":
                    yield _sse("thinking", {"content": chunk["content"]})

                elif chunk["type"] == "text":
                    assistant_text.append(chunk["content"])
                    yield _sse("token", {"content": chunk["content"]})

                elif chunk["type"] == "tool_used":
                    yield _sse("tool_used", {"tool": chunk["name"], "result": chunk["result"]})

                elif chunk["type"] == "done":
                    active_persona = chunk.get("persona", "ba")

            # Persist assistant message
            full_text = "".join(assistant_text)
            if full_text:
                db.add(Message(
                    project_id=project_id,
                    role="assistant",
                    content=full_text,
                    active_persona=active_persona,
                ))
                await db.commit()

            # Fresh snapshot (tool calls may have updated it this turn)
            snapshot = await KnowledgeService(db).get_snapshot(project_id)
            suggestions = get_suggestions(active_persona, snapshot)

            yield _sse("done", {"persona": active_persona, "suggestions": suggestions})

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


@router.get("/projects/{project_id}/knowledge-panel", response_class=HTMLResponse)
async def knowledge_panel(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    snapshot = await svc.get_snapshot(project_id)
    return templates.TemplateResponse(
        "partials/knowledge_panel.html",
        {"request": request, "snapshot": snapshot, "project_id": project_id},
    )
