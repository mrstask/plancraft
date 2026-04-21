"""ReAct evaluator loop — scaffolding for M0.

Roles become actors driven by a `LoopController`. Each actor output is scored
by an `EvaluatorProtocol`; if the score falls below the threshold the controller
re-invokes the actor with the evaluator's critique as feedback, up to
`max_iterations`. If `escalate_after` iterations have failed the controller
stops and returns `escalated=True` so the caller can hand off to the user.

M0 ships with `NullEvaluator` as the default for every role. No production
call path currently loops — the chat router uses `record_single_turn` to
write one trace row per role turn. `LoopController.run` exists, is fully
unit-tested, and is the extension point for M1+ when real evaluators are
plugged in.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from config import settings


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ActorOutput:
    """What one actor iteration produced."""
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    artifact_counts: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """What the evaluator thought of the actor's output."""
    score: float                                  # 0..1
    passed: bool                                  # score >= threshold (evaluator's view)
    critique: str = ""                            # feedback for the next iteration
    missing_items: list[str] = field(default_factory=list)
    rubric_version: str = "none"


@dataclass
class IterationTrace:
    iteration: int                                # 1-based
    actor_output: ActorOutput
    evaluator_result: EvaluationResult
    final: bool                                   # True for the last iteration of a turn
    critique_in: str | None = None                # critique fed INTO this iteration (None on iter 1)


@dataclass
class RoleRunResult:
    final_output: ActorOutput | None
    iterations: list[IterationTrace]
    converged: bool                                # evaluator accepted a result
    escalated: bool                                # escalated to user after escalate_after failed iters


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class ActorProtocol(Protocol):
    role: str

    async def run(self, context: dict, critique: str | None) -> ActorOutput: ...


class EvaluatorProtocol(Protocol):
    role: str
    rubric_version: str

    async def evaluate(self, actor_output: ActorOutput, context: dict) -> EvaluationResult: ...


PersisterFn = Callable[[IterationTrace], Awaitable[None]]
ActorFn = Callable[[dict, str | None], Awaitable[ActorOutput]]


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class LoopController:
    """Drives actor ↔ evaluator iterations.

    Settings default from `config.settings`; override in tests by passing
    explicit values to the constructor.
    """

    def __init__(
        self,
        max_iterations: int | None = None,
        score_threshold: float | None = None,
        escalate_after: int | None = None,
    ) -> None:
        self.max_iterations = (
            max_iterations if max_iterations is not None else settings.evaluator_max_iterations
        )
        self.score_threshold = (
            score_threshold if score_threshold is not None else settings.evaluator_score_threshold
        )
        self.escalate_after = (
            escalate_after if escalate_after is not None else settings.evaluator_escalate_after
        )
        if self.escalate_after > self.max_iterations:
            self.escalate_after = self.max_iterations

    async def run(
        self,
        actor: ActorFn,
        evaluator: EvaluatorProtocol,
        context: dict,
        persister: PersisterFn | None = None,
    ) -> RoleRunResult:
        """Run the actor / evaluator loop until convergence, escalation, or exhaustion."""
        traces: list[IterationTrace] = []
        critique_in: str | None = None
        final_output: ActorOutput | None = None
        converged = False
        escalated = False

        for iteration in range(1, self.max_iterations + 1):
            output = await _maybe_await(actor(context, critique_in))
            result = await _maybe_await(evaluator.evaluate(output, context))
            final_output = output

            accepted = result.passed and result.score >= self.score_threshold
            exhausted = iteration >= self.max_iterations
            would_escalate = (not accepted) and iteration >= self.escalate_after

            is_final = accepted or exhausted or would_escalate

            trace = IterationTrace(
                iteration=iteration,
                actor_output=output,
                evaluator_result=result,
                final=is_final,
                critique_in=critique_in,
            )
            traces.append(trace)
            if persister:
                await persister(trace)

            if accepted:
                converged = True
                break
            if would_escalate:
                escalated = True
                break
            critique_in = result.critique

        # Loop exited because max_iterations was hit without acceptance.
        if not converged and not escalated:
            escalated = True

        return RoleRunResult(
            final_output=final_output,
            iterations=traces,
            converged=converged,
            escalated=escalated,
        )


async def _maybe_await(value: Any) -> Any:
    """Allow evaluators and actors to be plain functions or coroutines."""
    if inspect.isawaitable(value):
        return await value
    return value


# ---------------------------------------------------------------------------
# Helpers used by the chat router
# ---------------------------------------------------------------------------


def build_actor_output(
    text: str,
    tool_calls: list[dict[str, Any]] | None = None,
    artifact_counts: dict[str, int] | None = None,
) -> ActorOutput:
    return ActorOutput(
        text=text or "",
        tool_calls=list(tool_calls or []),
        artifact_counts=dict(artifact_counts or {}),
    )
