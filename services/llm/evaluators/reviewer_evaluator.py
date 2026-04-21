"""Reviewer evaluator — M1 first real evaluator.

Parses the project constitution into rules, calls an LLM judge to check
whether the Reviewer's output violates any rules, and returns an
EvaluationResult with a score and per-violation critique.

The judge LLM call is isolated in `_call_judge` so tests can inject a stub
via `_judge_fn` without hitting a real Ollama instance.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from config import settings
from services.llm.react_loop import ActorOutput, EvaluationResult

log = logging.getLogger(__name__)

RUBRIC_VERSION = "reviewer-1"

_PLACEHOLDER_RE = re.compile(r"^\(.*\)$")


@dataclass
class Rule:
    section: str
    text: str
    severity: str  # "warn" | "block"


def parse_constitution_rules(md: str) -> list[Rule]:
    """Extract bullet-point rules from constitution markdown.

    Lines under `## Section` headings that start with `-` become rules.
    Severity defaults to `block` for bullets containing the word "must",
    `warn` otherwise. Placeholder lines like `(add NFR defaults...)` are
    skipped.
    """
    rules: list[Rule] = []
    current_section = "General"
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped[3:].strip()
        elif stripped.startswith("- "):
            text = stripped[2:].strip()
            if _PLACEHOLDER_RE.match(text):
                continue
            severity = "block" if re.search(r"\bmust\b", text, re.IGNORECASE) else "warn"
            rules.append(Rule(section=current_section, text=text, severity=severity))
    return rules


def build_judge_prompt(rules: list[Rule], reviewer_output: str) -> str:
    """Build a tight judge prompt: constitution rules + reviewer output only."""
    rule_lines = "\n".join(
        f"[{r.severity.upper()}] ({r.section}) {r.text}" for r in rules
    )
    return (
        "You are a strict quality checker. Given the project constitution rules below "
        "and the reviewer's output, identify any rules that are violated.\n\n"
        f"CONSTITUTION RULES:\n{rule_lines}\n\n"
        f"REVIEWER OUTPUT:\n{reviewer_output}\n\n"
        "For each violated rule write one line exactly as:\n"
        "VIOLATED: <rule text> | REASON: <one sentence explanation>\n\n"
        "If no rules are violated, write exactly: NO VIOLATIONS"
    )


def parse_judge_response(response: str, rules: list[Rule]) -> tuple[list[str], float]:
    """Parse the judge LLM response into (violations, score).

    Returns a list of violation descriptions and a 0..1 score.
    Score = 1 - (blocked_violations / max(total_block_rules, 1)).
    """
    block_rules = [r for r in rules if r.severity == "block"]
    violations: list[str] = []
    blocked_violations = 0

    for line in response.splitlines():
        if line.strip().startswith("VIOLATED:"):
            violation_text = line.strip()
            violations.append(violation_text)
            rule_fragment = violation_text.split("|")[0].replace("VIOLATED:", "").strip().lower()
            for r in block_rules:
                if r.text.lower()[:40] in rule_fragment or rule_fragment in r.text.lower():
                    blocked_violations += 1
                    break

    total_blocks = max(len(block_rules), 1)
    score = max(0.0, 1.0 - (blocked_violations / total_blocks))
    return violations, score


@dataclass
class ReviewerEvaluator:
    """Evaluates reviewer output against the project constitution.

    Inject `_judge_fn` in tests to avoid real LLM calls:

        ev = ReviewerEvaluator(_judge_fn=lambda prompt: "NO VIOLATIONS")
    """
    role: str = "review"
    rubric_version: str = RUBRIC_VERSION
    _judge_fn: Callable[[str], str | Awaitable[str]] | None = field(
        default=None, repr=False
    )

    async def evaluate(self, actor_output: ActorOutput, context: dict) -> EvaluationResult:
        constitution_md: str = context.get("constitution_md", "")
        rules = parse_constitution_rules(constitution_md)

        if not rules:
            return EvaluationResult(
                score=1.0,
                passed=True,
                critique="",
                rubric_version=self.rubric_version,
            )

        prompt = build_judge_prompt(rules, actor_output.text or "")
        response = await self._call_judge(prompt)
        violations, score = parse_judge_response(response, rules)

        has_block_violation = any(
            r.severity == "block"
            for r in rules
            if any(r.text.lower()[:40] in v.lower() for v in violations)
        )

        critique = "\n".join(violations) if violations else ""
        return EvaluationResult(
            score=score,
            passed=(not has_block_violation),
            critique=critique,
            missing_items=violations,
            rubric_version=self.rubric_version,
        )

    async def _call_judge(self, prompt: str) -> str:
        if self._judge_fn is not None:
            import inspect
            result = self._judge_fn(prompt)
            if inspect.isawaitable(result):
                return await result
            return result  # type: ignore[return-value]

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")
            response = await client.chat.completions.create(
                model=settings.evaluator_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            log.warning("Judge LLM call failed, treating as no violations: %s", exc)
            return "NO VIOLATIONS"
