"""Founder evaluator — checks the persisted founder artifacts."""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from database import AsyncSessionLocal
from services.knowledge.queries import ArtifactQueries
from services.llm.react_loop import ActorOutput, EvaluationResult

RUBRIC_VERSION = "founder-1"
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "their", "about", "have", "will", "what", "when", "where", "which",
    "while", "then", "than", "into", "onto", "build", "product", "users",
    "teams", "project", "clear", "ideas", "delivery", "plan", "plans",
    "software", "better",
}


@dataclass
class FounderState:
    mission_statement: str = ""
    mission_target_users: str = ""
    mission_problem: str = ""
    roadmap_items: list[dict] = field(default_factory=list)
    tech_stack_entries: list[dict] = field(default_factory=list)


@dataclass
class FounderEvaluator:
    role: str = "founder"
    rubric_version: str = RUBRIC_VERSION
    _loader_fn: Callable[[str], FounderState | Awaitable[FounderState]] | None = field(
        default=None,
        repr=False,
    )

    async def evaluate(self, actor_output: ActorOutput, context: dict) -> EvaluationResult:
        project_id = context.get("project_id")
        state = await self._load_state(project_id)

        mission_ok = self._check_mission_specificity(state)
        roadmap_ok = self._check_roadmap_coverage(state)
        rationale_ok = self._check_tech_rationales(state)
        mvp_ok = any(item.get("mvp") for item in state.roadmap_items)

        checks = {
            "Mission specificity": mission_ok,
            "Roadmap coverage": roadmap_ok,
            "Tech-stack rationale": rationale_ok,
            "MVP flag sanity": mvp_ok,
        }
        failures = [name for name, passed in checks.items() if not passed]
        score = sum(1 for passed in checks.values() if passed) / max(len(checks), 1)

        critique = ""
        if failures:
            critique = "\n".join(f"Missing or weak: {name}" for name in failures)

        return EvaluationResult(
            score=score,
            passed=not failures,
            critique=critique,
            missing_items=failures,
            rubric_version=self.rubric_version,
        )

    async def _load_state(self, project_id: str | None) -> FounderState:
        if self._loader_fn is not None:
            state = self._loader_fn(project_id or "")
            if inspect.isawaitable(state):
                return await state
            return state

        if not project_id:
            return FounderState()

        async with AsyncSessionLocal() as session:
            queries = ArtifactQueries(session)
            mission = await queries.get_project_mission(project_id)
            roadmap_items = await queries.get_all_roadmap_items(project_id)
            tech_entries = await queries.get_all_tech_stack_entries(project_id)
            return FounderState(
                mission_statement=mission.statement if mission else "",
                mission_target_users=mission.target_users if mission else "",
                mission_problem=mission.problem if mission else "",
                roadmap_items=[
                    {
                        "title": item.title,
                        "description": item.description,
                        "mvp": bool(item.mvp),
                    }
                    for item in roadmap_items
                ],
                tech_stack_entries=[
                    {
                        "layer": entry.layer,
                        "choice": entry.choice,
                        "rationale": entry.rationale,
                    }
                    for entry in tech_entries
                ],
            )

    def _check_mission_specificity(self, state: FounderState) -> bool:
        statement = state.mission_statement.strip()
        if not statement or not state.mission_target_users.strip() or not state.mission_problem.strip():
            return False
        sentences = [s for s in re.split(r"[.!?]+", statement) if s.strip()]
        if len(sentences) > 2:
            return False
        lowered = statement.lower()
        has_outcome = any(token in lowered for token in ("help", "enable", "allow", "so ", "deliver", "give"))
        return has_outcome or len(statement.split()) >= 8

    def _check_roadmap_coverage(self, state: FounderState) -> bool:
        if not state.roadmap_items:
            return False
        mission_keywords = set(self._goal_keywords(f"{state.mission_statement} {state.mission_problem}"))
        if not mission_keywords:
            return True
        roadmap_keywords = set(
            self._goal_keywords(
                " ".join(
                    f"{item.get('title', '')} {item.get('description', '')}"
                    for item in state.roadmap_items
                )
            )
        )
        return bool(mission_keywords & roadmap_keywords) or any(
            len((item.get("description") or "").strip()) >= 40
            for item in state.roadmap_items
        )

    def _check_tech_rationales(self, state: FounderState) -> bool:
        if not state.tech_stack_entries:
            return False
        return all(len((entry.get("rationale") or "").strip()) > 40 for entry in state.tech_stack_entries)

    def _goal_keywords(self, text: str) -> list[str]:
        keywords: list[str] = []
        for token in re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower()):
            if token in _STOPWORDS:
                continue
            if token not in keywords:
                keywords.append(token)
            if len(keywords) >= 5:
                break
        return keywords
