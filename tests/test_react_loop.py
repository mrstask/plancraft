"""Unit tests for the M0 ReAct evaluator loop."""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Callable

from services.llm.react_loop import (
    ActorOutput,
    EvaluationResult,
    IterationTrace,
    LoopController,
)


@dataclass
class StubEvaluator:
    """Test-only evaluator driven by a supplied scoring function."""
    role: str = "ba"
    rubric_version: str = "test-1"
    scorer: Callable[[ActorOutput, int], EvaluationResult] = None  # type: ignore[assignment]
    _call_count: int = 0

    async def evaluate(self, actor_output: ActorOutput, context: dict) -> EvaluationResult:
        self._call_count += 1
        assert self.scorer is not None
        return self.scorer(actor_output, self._call_count)


@dataclass
class RecordingActor:
    """Counts how many times it was called and what critiques it saw."""
    calls: list[str | None] = field(default_factory=list)
    output_factory: Callable[[int], ActorOutput] = field(
        default_factory=lambda: (lambda i: ActorOutput(text=f"attempt {i}"))
    )

    def as_fn(self):
        async def _fn(context: dict, critique: str | None) -> ActorOutput:
            self.calls.append(critique)
            return self.output_factory(len(self.calls))
        return _fn


def _pass(score: float = 1.0, critique: str = "") -> EvaluationResult:
    return EvaluationResult(score=score, passed=True, critique=critique, rubric_version="test-1")


def _fail(score: float = 0.1, critique: str = "missing things") -> EvaluationResult:
    return EvaluationResult(score=score, passed=False, critique=critique, rubric_version="test-1")


class LoopControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_converges_on_first_pass(self):
        controller = LoopController(max_iterations=3, score_threshold=0.8, escalate_after=2)
        actor = RecordingActor()
        evaluator = StubEvaluator(scorer=lambda out, n: _pass())

        persisted: list[IterationTrace] = []

        async def persister(trace):
            persisted.append(trace)

        result = await controller.run(actor.as_fn(), evaluator, {}, persister)

        self.assertTrue(result.converged)
        self.assertFalse(result.escalated)
        self.assertEqual(len(result.iterations), 1)
        self.assertEqual(len(actor.calls), 1)
        self.assertIsNone(actor.calls[0])
        self.assertTrue(result.iterations[0].final)
        self.assertTrue(persisted[0].final)

    async def test_retries_with_critique_then_passes(self):
        controller = LoopController(max_iterations=3, score_threshold=0.8, escalate_after=3)

        def scorer(out, n):
            return _fail(critique="needs acceptance criteria") if n == 1 else _pass()

        actor = RecordingActor()
        evaluator = StubEvaluator(scorer=scorer)

        result = await controller.run(actor.as_fn(), evaluator, {})

        self.assertTrue(result.converged)
        self.assertFalse(result.escalated)
        self.assertEqual(len(result.iterations), 2)
        self.assertEqual(actor.calls, [None, "needs acceptance criteria"])
        # First iteration is not final; second is.
        self.assertFalse(result.iterations[0].final)
        self.assertTrue(result.iterations[1].final)

    async def test_escalates_after_configured_failures(self):
        controller = LoopController(max_iterations=5, score_threshold=0.8, escalate_after=2)
        actor = RecordingActor()
        evaluator = StubEvaluator(scorer=lambda out, n: _fail())

        result = await controller.run(actor.as_fn(), evaluator, {})

        self.assertFalse(result.converged)
        self.assertTrue(result.escalated)
        self.assertEqual(len(result.iterations), 2)  # escalate_after=2 → stop after iter 2
        self.assertTrue(result.iterations[-1].final)

    async def test_hits_max_iterations_without_convergence(self):
        # escalate_after larger than max_iterations: loop exhausts instead of escalating early
        controller = LoopController(max_iterations=2, score_threshold=0.8, escalate_after=5)
        # constructor clamps escalate_after to max_iterations
        self.assertEqual(controller.escalate_after, 2)

        actor = RecordingActor()
        evaluator = StubEvaluator(scorer=lambda out, n: _fail())

        result = await controller.run(actor.as_fn(), evaluator, {})

        self.assertFalse(result.converged)
        self.assertTrue(result.escalated)
        self.assertEqual(len(result.iterations), 2)
        # Exactly one final row per turn, always the last iteration.
        finals = [t for t in result.iterations if t.final]
        self.assertEqual(len(finals), 1)
        self.assertIs(finals[0], result.iterations[-1])

    async def test_threshold_override_beats_evaluator_passed_flag(self):
        # evaluator says passed=True but score is below controller's threshold → retry
        controller = LoopController(max_iterations=3, score_threshold=0.9, escalate_after=3)

        def scorer(out, n):
            if n == 1:
                return EvaluationResult(score=0.85, passed=True, critique="weak", rubric_version="test-1")
            return EvaluationResult(score=0.95, passed=True, rubric_version="test-1")

        actor = RecordingActor()
        evaluator = StubEvaluator(scorer=scorer)

        result = await controller.run(actor.as_fn(), evaluator, {})
        self.assertTrue(result.converged)
        self.assertEqual(len(result.iterations), 2)

    async def test_null_evaluator_always_converges(self):
        from services.llm.evaluators import NullEvaluator

        controller = LoopController(max_iterations=3)
        actor = RecordingActor()
        result = await controller.run(actor.as_fn(), NullEvaluator(role="ba"), {})

        self.assertTrue(result.converged)
        self.assertEqual(len(result.iterations), 1)
        self.assertEqual(result.iterations[0].evaluator_result.score, 1.0)


class EvaluatorRegistryTests(unittest.TestCase):
    def test_get_evaluator_defaults_to_null(self):
        from services.llm.evaluators import NullEvaluator, get_evaluator

        ev = get_evaluator("ba")
        self.assertIsInstance(ev, NullEvaluator)
        self.assertEqual(ev.role, "ba")

    def test_registered_evaluator_wins(self):
        from services.llm.evaluators import get_evaluator, register_evaluator

        class FakeEvaluator:
            role = "architect"
            rubric_version = "x"

            async def evaluate(self, a, c):
                return _pass()

        register_evaluator("architect", FakeEvaluator())
        try:
            ev = get_evaluator("architect")
            self.assertEqual(ev.rubric_version, "x")
        finally:
            # Clean up registry so other tests see defaults.
            from services.llm.evaluators import _REGISTRY
            _REGISTRY.pop("architect", None)


class RubricLoaderTests(unittest.TestCase):
    def test_known_role_loads(self):
        from services.llm.rubrics import load_rubric

        rubric = load_rubric("ba")
        self.assertIn("version", rubric)
        self.assertIsInstance(rubric["rules"], list)
        self.assertGreater(len(rubric["rules"]), 0)

    def test_missing_role_returns_empty_rubric(self):
        from services.llm.rubrics import load_rubric

        rubric = load_rubric("does-not-exist")
        self.assertEqual(rubric["rules"], [])


if __name__ == "__main__":
    unittest.main()
