"""Prompt builders for phase-specific planning roles."""
from __future__ import annotations

from models.domain import KnowledgeSnapshot
from roles import (
    ArchitectRole,
    BusinessAnalystRole,
    ProductManagerRole,
    ReviewerRole,
    TDDTesterRole,
)

ROLE_MAP = {
    "ba": BusinessAnalystRole,
    "pm": ProductManagerRole,
    "architect": ArchitectRole,
    "tdd": TDDTesterRole,
    "review": ReviewerRole,
}

PHASE_TOOL_RULES = {
    "ba": (
        "- When you articulate or refine the problem statement -> call set_problem_statement().\n"
        "- When you identify a user story -> call add_user_story() immediately.\n"
        "- When you refine an existing story -> call update_user_story().\n"
        "- When you note a constraint -> call record_constraint().\n"
        "- IMPORTANT: Always write your conversational reply in the same response as any tool calls.\n"
        "  Never call tools silently — the user must receive a visible text response every turn.\n"
    ),
    "pm": (
        "- When you define or refine an epic -> call add_epic().\n"
        "- When you update a story's priority or wording -> call update_user_story().\n"
        "- When you lock the MVP cut -> call set_mvp_scope() with the selected story IDs.\n"
        "- IMPORTANT: Always write your conversational reply in the same response as any tool calls.\n"
        "  Never call tools silently — the user must receive a visible text response every turn.\n"
    ),
    "architect": (
        "- When you propose a component -> call add_component() immediately, one call per component.\n"
        "- When you make an architecture decision -> call record_decision() immediately.\n"
        "- When you note a technical constraint -> call record_constraint().\n"
        "- IMPORTANT: Always write your conversational reply in the same response as any tool calls.\n"
        "  Never call tools silently — the user must receive a visible text response every turn.\n"
    ),
    "tdd": (
        "- Every test spec you think of -> call add_test_spec() in this response.\n"
        "- Every implementation task -> call propose_task() in this response.\n"
        "- Do not leave specs or tasks described only in prose.\n"
        "- Cover all components visible in the project state unless the user narrows the scope.\n"
    ),
    "review": (
        "- When you find a duplicate artifact -> call delete_* immediately.\n"
        "- When wording needs improvement -> call update_* immediately.\n"
        "- Use the artifact IDs shown in the context exactly as provided.\n"
    ),
}


def build_system_prompt(
    snapshot: KnowledgeSnapshot,
    role_tab: str = "ba",
    full_context: str | None = None,
) -> str:
    role = ROLE_MAP.get(role_tab, BusinessAnalystRole)()
    tool_rules = PHASE_TOOL_RULES.get(role_tab, "")

    return f"""You are a software planning assistant acting as {role.name} for this project.

{role.system_prompt_fragment}

## Mandatory Tool-Calling Rules
You have tools to persist structured knowledge. Follow these rules every turn:

{tool_rules}
Call tools in the same turn you discuss the item.
Do not describe a persistable artifact in text without calling the matching tool.
NEVER write tool-call syntax as text (e.g. `add_epic{{title: ...}}` or `add_epic(...)`).
Tool calls MUST use the structured tool_calls API — if you type the function name in your
prose, it does NOT execute and the artifact will NOT be saved.
You may briefly confirm after calling: "Saved." or "Noted."

## Behaviour
- Ask one focused question at a time unless the current phase explicitly calls for bulk generation.
- Push back on vague requirements.
- Keep responses concise and conversational.
- When you have enough material for this phase, suggest moving to the next one.

## Current Project State
{full_context if full_context is not None else snapshot.to_context_string()}
"""
