"""Persistence + query helpers for `role_execution_traces`.

Kept in its own module (outside `services/knowledge/`) because traces are a
cross-cutting concern, not a typed knowledge artifact: they describe the
LLM execution, not the project's domain content.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.db import RoleExecutionTrace

from .react_loop import ActorOutput, EvaluationResult, IterationTrace


def _serialize_actor_output(output: ActorOutput) -> str:
    """Flatten ActorOutput into a string for the `actor_output` text column."""
    payload = {
        "text": output.text,
        "tool_calls": output.tool_calls,
        "artifact_counts": output.artifact_counts,
    }
    return json.dumps(payload, ensure_ascii=False)


async def persist_iteration_trace(
    db: AsyncSession,
    *,
    project_id: str,
    role: str,
    iteration: int,
    actor_prompt: str,
    actor_output: ActorOutput,
    evaluator_result: EvaluationResult,
    final: bool,
    feature_id: str | None = None,
    commit: bool = True,
) -> RoleExecutionTrace:
    """Insert a single iteration row. Call once per LoopController iteration."""
    row = RoleExecutionTrace(
        project_id=project_id,
        feature_id=feature_id,
        role=role,
        iteration=iteration,
        actor_prompt=actor_prompt or "",
        actor_output=_serialize_actor_output(actor_output),
        evaluator_score=evaluator_result.score,
        evaluator_critique=evaluator_result.critique or None,
        rubric_version=evaluator_result.rubric_version,
        final=final,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


async def record_single_turn(
    db: AsyncSession,
    *,
    project_id: str,
    role: str,
    actor_prompt: str,
    actor_output: ActorOutput,
    evaluator,
    feature_id: str | None = None,
    context: dict | None = None,
) -> RoleExecutionTrace:
    """Production-path helper used by the chat router.

    The live chat stream has already produced its output by the time we get
    here, so we cannot re-invoke the actor mid-turn. Instead we evaluate the
    completed output once and persist the result as iteration=1, final=True.
    Pass extra context (e.g. `constitution_md`) via the `context` kwarg.
    """
    eval_context = {"project_id": project_id, "role": role, **(context or {})}
    result = await evaluator.evaluate(actor_output, eval_context)
    return await persist_iteration_trace(
        db,
        project_id=project_id,
        role=role,
        iteration=1,
        actor_prompt=actor_prompt,
        actor_output=actor_output,
        evaluator_result=result,
        final=True,
        feature_id=feature_id,
    )


async def get_traces_for_project(
    db: AsyncSession,
    project_id: str,
    *,
    role: str | None = None,
    limit: int = 20,
    only_final: bool = False,
) -> list[RoleExecutionTrace]:
    stmt = select(RoleExecutionTrace).where(RoleExecutionTrace.project_id == project_id)
    if role:
        stmt = stmt.where(RoleExecutionTrace.role == role)
    if only_final:
        stmt = stmt.where(RoleExecutionTrace.final.is_(True))
    stmt = stmt.order_by(RoleExecutionTrace.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def deserialize_actor_output(raw: str) -> dict:
    """Inverse of `_serialize_actor_output` for UI rendering."""
    if not raw:
        return {"text": "", "tool_calls": [], "artifact_counts": {}}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw, "tool_calls": [], "artifact_counts": {}}


async def prune_old_traces(db: AsyncSession, *, keep_final: bool = True) -> int:
    """Delete non-final traces older than `settings.trace_retention_days`.

    Intentionally conservative: final rows are preserved by default so that
    the history of accepted turns stays queryable indefinitely.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.trace_retention_days)
    stmt = delete(RoleExecutionTrace).where(RoleExecutionTrace.created_at < cutoff)
    if keep_final:
        stmt = stmt.where(RoleExecutionTrace.final.is_(False))
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
