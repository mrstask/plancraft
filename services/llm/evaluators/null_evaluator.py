"""NullEvaluator — always passes with score 1.0.

Used as the default for every role until a real evaluator is registered.
Keeps the `LoopController` wired into every role path from M0 so later
milestones only have to register an evaluator, not refactor call sites.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.llm.react_loop import ActorOutput, EvaluationResult


@dataclass
class NullEvaluator:
    role: str = "*"
    rubric_version: str = "null-0"

    async def evaluate(self, actor_output: ActorOutput, context: dict) -> EvaluationResult:
        return EvaluationResult(
            score=1.0,
            passed=True,
            critique="",
            missing_items=[],
            rubric_version=self.rubric_version,
        )
