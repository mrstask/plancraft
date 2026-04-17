"""Chat routes — SSE streaming endpoint."""
import json
import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from database import get_db
from models.db import Message
from services.claude import stream_response
from services.knowledge import KnowledgeService

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


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

    # Build message history for Claude
    result = await db.execute(
        select(Message)
        .where(Message.project_id == project_id)
        .order_by(Message.created_at.asc())
    )
    all_messages = result.scalars().all()

    claude_messages = [
        {"role": m.role, "content": m.content}
        for m in all_messages
    ]

    # SSE stream
    async def event_generator():
        assistant_text = []
        active_persona = "ba"

        try:
            async for chunk in stream_response(project_id, claude_messages, db):
                if chunk["type"] == "text":
                    assistant_text.append(chunk["content"])
                    # Stream token to browser
                    yield {
                        "event": "token",
                        "data": json.dumps({"content": chunk["content"]}),
                    }

                elif chunk["type"] == "tool_used":
                    # Notify browser to refresh the knowledge panel
                    yield {
                        "event": "tool_used",
                        "data": json.dumps({
                            "tool": chunk["name"],
                            "result": chunk["result"],
                        }),
                    }

                elif chunk["type"] == "done":
                    active_persona = chunk.get("persona", "ba")

            # Persist the full assistant message
            full_text = "".join(assistant_text)
            if full_text:
                assistant_msg = Message(
                    project_id=project_id,
                    role="assistant",
                    content=full_text,
                    active_persona=active_persona,
                )
                db.add(assistant_msg)
                await db.commit()

            yield {
                "event": "done",
                "data": json.dumps({"persona": active_persona}),
            }

        except Exception as e:
            log.error(f"Stream error: {e}", exc_info=True)
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@router.get("/projects/{project_id}/knowledge-panel", response_class=HTMLResponse)
async def knowledge_panel(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Returns the right panel HTML — called by HTMX after tool_used events."""
    svc = KnowledgeService(db)
    snapshot = await svc.get_snapshot(project_id)
    return templates.TemplateResponse(
        "partials/knowledge_panel.html",
        {"request": request, "snapshot": snapshot, "project_id": project_id},
    )
