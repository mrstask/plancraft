"""Tests for ReviewerEvaluator — M1."""
from __future__ import annotations

import unittest

from services.llm.evaluators.reviewer_evaluator import (
    Rule,
    build_judge_prompt,
    parse_constitution_rules,
    parse_judge_response,
    ReviewerEvaluator,
)
from services.llm.react_loop import ActorOutput


SAMPLE_CONSTITUTION = """
# Constitution

## Quality rules
- All user stories must have at least one acceptance criterion.
- All components must be referenced by at least one story.

## Testing
- Every user story requires at least one Given/When/Then test spec.

## Non-functional defaults
- (add NFR defaults the project inherits unless overridden)

## Naming
- Component names should be unique.
"""


class ParseConstitutionRulesTests(unittest.TestCase):
    def test_extracts_rules_from_sample(self):
        rules = parse_constitution_rules(SAMPLE_CONSTITUTION)
        texts = [r.text for r in rules]
        self.assertIn("All user stories must have at least one acceptance criterion.", texts)
        self.assertIn("Component names should be unique.", texts)

    def test_skips_placeholder_lines(self):
        rules = parse_constitution_rules(SAMPLE_CONSTITUTION)
        texts = [r.text for r in rules]
        for t in texts:
            self.assertFalse(t.startswith("("), f"Placeholder not skipped: {t!r}")

    def test_severity_block_for_must(self):
        rules = parse_constitution_rules(SAMPLE_CONSTITUTION)
        must_rules = [r for r in rules if "must" in r.text.lower()]
        self.assertTrue(all(r.severity == "block" for r in must_rules))

    def test_severity_warn_for_should(self):
        rules = parse_constitution_rules(SAMPLE_CONSTITUTION)
        should_rules = [r for r in rules if "should" in r.text.lower() and "must" not in r.text.lower()]
        self.assertTrue(all(r.severity == "warn" for r in should_rules))

    def test_section_assigned(self):
        rules = parse_constitution_rules(SAMPLE_CONSTITUTION)
        quality_rules = [r for r in rules if "acceptance criterion" in r.text]
        self.assertEqual(quality_rules[0].section, "Quality rules")

    def test_empty_constitution_returns_no_rules(self):
        self.assertEqual(parse_constitution_rules(""), [])

    def test_constitution_without_headings(self):
        md = "- All stories must have AC.\n- Tests should exist.\n"
        rules = parse_constitution_rules(md)
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].severity, "block")
        self.assertEqual(rules[1].severity, "warn")


class BuildJudgePromptTests(unittest.TestCase):
    def test_prompt_contains_rules_and_output(self):
        rules = [
            Rule(section="Quality", text="All stories must have AC.", severity="block"),
        ]
        prompt = build_judge_prompt(rules, "The reviewer found no issues.")
        self.assertIn("All stories must have AC.", prompt)
        self.assertIn("The reviewer found no issues.", prompt)
        self.assertIn("VIOLATED:", prompt)
        self.assertIn("NO VIOLATIONS", prompt)


class ParseJudgeResponseTests(unittest.TestCase):
    def _rules(self):
        return [
            Rule("Quality", "All stories must have AC.", "block"),
            Rule("Testing", "Every story requires a test spec.", "block"),
            Rule("Naming", "Names should be unique.", "warn"),
        ]

    def test_no_violations_returns_full_score(self):
        violations, score = parse_judge_response("NO VIOLATIONS", self._rules())
        self.assertEqual(violations, [])
        self.assertEqual(score, 1.0)

    def test_violation_line_is_captured(self):
        response = "VIOLATED: All stories must have AC. | REASON: Story US-001 has no AC."
        violations, score = parse_judge_response(response, self._rules())
        self.assertEqual(len(violations), 1)
        self.assertLess(score, 1.0)

    def test_score_decreases_per_block_violation(self):
        response = (
            "VIOLATED: All stories must have AC. | REASON: US-001 missing.\n"
            "VIOLATED: Every story requires a test spec. | REASON: No specs at all."
        )
        violations, score = parse_judge_response(response, self._rules())
        self.assertEqual(len(violations), 2)
        self.assertLessEqual(score, 0.0)


class ReviewerEvaluatorTests(unittest.IsolatedAsyncioTestCase):
    def _evaluator(self, judge_response: str) -> ReviewerEvaluator:
        return ReviewerEvaluator(_judge_fn=lambda _prompt: judge_response)

    async def test_no_constitution_passes_immediately(self):
        ev = ReviewerEvaluator()
        output = ActorOutput(text="reviewer output")
        result = await ev.evaluate(output, {"constitution_md": ""})
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)

    async def test_no_violations_passes(self):
        ev = self._evaluator("NO VIOLATIONS")
        output = ActorOutput(text="All stories have AC.")
        result = await ev.evaluate(output, {"constitution_md": SAMPLE_CONSTITUTION})
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.critique, "")

    async def test_block_violation_fails(self):
        violation = "VIOLATED: All user stories must have at least one acceptance criterion. | REASON: US-001 missing AC."
        ev = self._evaluator(violation)
        output = ActorOutput(text="Some stories are missing AC.")
        result = await ev.evaluate(output, {"constitution_md": SAMPLE_CONSTITUTION})
        self.assertFalse(result.passed)
        self.assertLess(result.score, 1.0)
        self.assertIn("VIOLATED", result.critique)

    async def test_rubric_version_set(self):
        ev = self._evaluator("NO VIOLATIONS")
        result = await ev.evaluate(ActorOutput(), {"constitution_md": SAMPLE_CONSTITUTION})
        self.assertEqual(result.rubric_version, "reviewer-1")

    async def test_loop_converges_after_critique(self):
        """Two-iteration loop: first fails, second passes when critique is applied."""
        from services.llm.react_loop import LoopController

        call_count = 0

        def judge(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "VIOLATED: All user stories must have at least one acceptance criterion. | REASON: missing"
            return "NO VIOLATIONS"

        ev = ReviewerEvaluator(_judge_fn=judge)
        controller = LoopController(max_iterations=3, score_threshold=0.8, escalate_after=3)

        async def actor(context, critique):
            return ActorOutput(text="improved output" if critique else "first output")

        result = await controller.run(actor, ev, {"constitution_md": SAMPLE_CONSTITUTION})
        self.assertTrue(result.converged)
        self.assertEqual(len(result.iterations), 2)
        self.assertEqual(call_count, 2)

    async def test_loop_escalates_on_persistent_violations(self):
        from services.llm.react_loop import LoopController
        ev = self._evaluator(
            "VIOLATED: All user stories must have at least one acceptance criterion. | REASON: none"
        )
        controller = LoopController(max_iterations=3, score_threshold=0.8, escalate_after=2)

        async def actor(context, critique):
            return ActorOutput(text="output")

        result = await controller.run(actor, ev, {"constitution_md": SAMPLE_CONSTITUTION})
        self.assertFalse(result.converged)
        self.assertTrue(result.escalated)
        self.assertEqual(len(result.iterations), 2)


if __name__ == "__main__":
    unittest.main()
