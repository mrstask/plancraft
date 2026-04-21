"""Rule-based next-step suggestion generator.

Produces 2-3 contextual chips based on what the knowledge model currently
contains — no extra LLM call needed.
"""
from __future__ import annotations
from models.domain import KnowledgeSnapshot


def get_suggestions(persona: str, snapshot: KnowledgeSnapshot) -> list[str]:
    has_mission    = bool(snapshot.mission_statement)
    has_roadmap    = snapshot.roadmap_item_count > 0
    has_tech_stack = snapshot.tech_stack_count > 0
    has_problem    = bool(snapshot.problem_statement)
    has_mvp_scope  = snapshot.mvp_story_count > 0
    has_stories    = snapshot.story_count > 0
    has_epics      = snapshot.epic_count > 0
    has_components = snapshot.component_count > 0
    has_decisions  = snapshot.decision_count > 0
    has_tests      = snapshot.test_spec_count > 0
    has_tasks      = snapshot.task_count > 0

    # ── Stage 0: founder framing not captured yet ─────────────────────────
    if not has_mission or not has_roadmap or not has_tech_stack:
        return [
            "Who is this product for, and what outcome should it create?",
            "What are the 2-3 biggest roadmap outcomes after launch?",
            "What stack do you want to standardize on for v1?",
        ]

    # ── Stage 1: nothing captured yet beyond founder framing ──────────────
    if not has_problem and not has_stories:
        return [
            "Who are the users and what frustrates them?",
            "What does success look like for this project?",
            "Give me one concrete example of how someone uses this",
        ]

    # ── Stage 2: problem set, no stories yet ───────────────────────────────
    if has_problem and not has_stories:
        return [
            "Let's capture the first user story",
            "What's the single most important feature for v1?",
            "Are there different types of users with different needs?",
        ]

    # ── Stage 3: stories exist, no architecture yet ────────────────────────
    if has_stories and not has_components:
        if not has_epics:
            return [
                "Group these stories into epics",
                "Which stories are must-haves for the MVP?",
                "Let's start designing the architecture",
            ]
        if not has_mvp_scope:
            return [
                "Which stories are must-haves for the MVP?",
                "What's the rationale for the MVP cut?",
                "Let's start designing the architecture",
            ]
        return [
            "Let's design the main components",
            "What are the biggest technical constraints?",
            "Should we revisit the MVP cut before architecture?",
        ]

    # ── Stage 4: architecture started, no test specs ───────────────────────
    if has_components and not has_tests:
        if not has_decisions:
            return [
                "Record the key architecture decisions",
                "Write test specs for the main component",
                "What could go wrong with this design?",
            ]
        return [
            "Write test specs for the main component",
            "What are the edge cases we need to handle?",
            "Define acceptance criteria for the top story",
        ]

    # ── Stage 5: tests exist, no tasks yet ─────────────────────────────────
    if has_tests and not has_tasks:
        return [
            "Break this into independent implementation tasks",
            "What can be built in parallel?",
            "Generate the full task list for the dev team",
        ]

    # ── Stage 6: full model — offer refinement or export ───────────────────
    suggestions = []
    if snapshot.story_count < 5:
        suggestions.append("Add more user stories")
    if not has_decisions:
        suggestions.append("Record architecture decisions")
    suggestions.append("Export the task list for the dev team")
    suggestions.append("Preview the arc42 documentation")
    return suggestions[:3]
