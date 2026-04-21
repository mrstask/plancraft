from __future__ import annotations

import unittest

from services.llm.evaluators.founder_evaluator import FounderEvaluator, FounderState
from services.llm.react_loop import ActorOutput, LoopController


class FounderEvaluatorTests(unittest.IsolatedAsyncioTestCase):
    def _state(self, *, rationale: str, mvp: bool = True) -> FounderState:
        return FounderState(
            mission_statement="Help product teams turn ideas into a delivery plan.",
            mission_target_users="product teams",
            mission_problem="Planning context is fragmented across too many artifacts.",
            roadmap_items=[
                {
                    "title": "Launch the core planning workflow",
                    "description": "Ship the first workflow so teams can capture, review, and align on project goals quickly.",
                    "mvp": mvp,
                }
            ],
            tech_stack_entries=[
                {
                    "layer": "backend",
                    "choice": "FastAPI",
                    "rationale": rationale,
                }
            ],
        )

    async def test_missing_rationale_fails(self):
        ev = FounderEvaluator(_loader_fn=lambda _pid: self._state(rationale="Too short"))
        result = await ev.evaluate(ActorOutput(text="founder output"), {"project_id": "p1"})
        self.assertFalse(result.passed)
        self.assertIn("Tech-stack rationale", result.missing_items)

    async def test_missing_mvp_fails(self):
        ev = FounderEvaluator(_loader_fn=lambda _pid: self._state(
            rationale="This keeps the product in the existing Python stack and minimizes operational overhead for the v1 release.",
            mvp=False,
        ))
        result = await ev.evaluate(ActorOutput(text="founder output"), {"project_id": "p1"})
        self.assertFalse(result.passed)
        self.assertIn("MVP flag sanity", result.missing_items)

    async def test_loop_converges_after_feedback(self):
        call_count = 0

        async def load_state(_pid: str) -> FounderState:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._state(rationale="Too short", mvp=False)
            return self._state(
                rationale="This stays aligned with the current Python service stack, is quick for the team to extend, and keeps deployment complexity low for the MVP.",
                mvp=True,
            )

        controller = LoopController(max_iterations=3, score_threshold=0.8, escalate_after=3)
        evaluator = FounderEvaluator(_loader_fn=load_state)

        async def actor(_context, critique):
            return ActorOutput(text="improved founder output" if critique else "first founder output")

        result = await controller.run(actor, evaluator, {"project_id": "p1"})
        self.assertTrue(result.converged)
        self.assertEqual(len(result.iterations), 2)
