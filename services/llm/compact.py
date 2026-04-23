"""Dialog compaction — summarize an active role/feature dialog to free context."""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.db import Message
from .streaming import client

log = logging.getLogger(__name__)


_COMPACT_SYSTEM = (
    "You are a dialog-compaction assistant. Given a chronological dialog between a user "
    "and a planning-assistant role, produce a dense summary that preserves:\n"
    "- the user's stated goals, constraints, and preferences;\n"
    "- every decision that was agreed on;\n"
    "- open questions / clarification points still outstanding;\n"
    "- the most recent state of the work so the role can pick up where it left off.\n"
    "Discard pleasantries, restated context, and intermediate brainstorming. "
    "Write in third person, in bullet sections: ## Decisions, ## Open questions, "
    "## Current state, ## User preferences. No preamble, no sign-off."
)


async def compact_dialog(
    db: AsyncSession,
    project_id: str,
    role_tab: str,
    feature_id: str | None,
) -> dict:
    """Summarize the active non-archived messages for this (role_tab, feature) dialog.

    Archives the old messages and inserts one assistant message tagged kind='summary'.
    Returns a dict with the summary text and counts.
    """
    stmt = (
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.role_tab == role_tab,
            Message.archived == False,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    if feature_id is None:
        stmt = stmt.where(Message.feature_id.is_(None))
    else:
        stmt = stmt.where(Message.feature_id == feature_id)

    rows = (await db.execute(stmt)).scalars().all()
    # Keep the last N messages untouched so the user still sees recent context.
    keep_tail = max(0, settings.compact_keep_tail)
    if len(rows) <= keep_tail + 1:
        return {"summary": None, "archived": 0, "message": "Dialog is already short."}

    to_compact = rows[:-keep_tail] if keep_tail else rows
    tail = rows[-keep_tail:] if keep_tail else []

    transcript_parts = []
    for m in to_compact:
        who = "User" if m.role == "user" else "Assistant"
        transcript_parts.append(f"{who}: {m.content}")
    transcript = "\n\n".join(transcript_parts)

    resp = await client.chat.completions.create(
        model=settings.ollama_model,
        max_tokens=settings.max_tokens,
        messages=[
            {"role": "system", "content": _COMPACT_SYSTEM},
            {"role": "user", "content": (
                f"Dialog role: {role_tab}\n"
                f"Feature-scoped: {'yes' if feature_id else 'no'}\n\n"
                f"--- transcript ---\n{transcript}\n--- end ---"
            )},
        ],
        stream=False,
    )
    summary_text = (resp.choices[0].message.content or "").strip()
    if not summary_text:
        summary_text = "(Compaction produced no summary — please retry.)"

    ids = [m.id for m in to_compact]
    await db.execute(
        update(Message).where(Message.id.in_(ids)).values(archived=True)
    )

    # Insert the summary as an assistant message tagged as kind='summary' so
    # future turns see it as context but the UI can style it distinctly.
    summary_msg = Message(
        project_id=project_id,
        role="assistant",
        content=f"**Dialog summary (compacted {len(ids)} messages):**\n\n{summary_text}",
        active_persona=role_tab,
        role_tab=role_tab,
        feature_id=feature_id,
        kind="summary",
    )
    db.add(summary_msg)
    await db.commit()
    await db.refresh(summary_msg)

    return {
        "summary": summary_text,
        "archived": len(ids),
        "kept": len(tail),
        "summary_message_id": summary_msg.id,
    }
