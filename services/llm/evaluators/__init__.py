"""Evaluator registry.

Real evaluators register themselves here in later milestones. Until a role
has a registered evaluator, `get_evaluator(role)` returns `NullEvaluator`,
which always passes.
"""
from __future__ import annotations

from services.llm.react_loop import EvaluatorProtocol

from .founder_evaluator import FounderEvaluator
from .null_evaluator import NullEvaluator
from .reviewer_evaluator import ReviewerEvaluator

_REGISTRY: dict[str, EvaluatorProtocol] = {
    "founder": FounderEvaluator(),
    "review": ReviewerEvaluator(),
}


def register_evaluator(role: str, evaluator: EvaluatorProtocol) -> None:
    _REGISTRY[role] = evaluator


def get_evaluator(role: str) -> EvaluatorProtocol:
    """Return the registered evaluator for a role, or NullEvaluator as default."""
    return _REGISTRY.get(role, NullEvaluator(role=role))


__all__ = [
    "register_evaluator",
    "get_evaluator",
    "FounderEvaluator",
    "NullEvaluator",
    "ReviewerEvaluator",
]
