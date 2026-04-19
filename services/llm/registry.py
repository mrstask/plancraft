"""Central registry for LLM tool schemas and dispatch."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from models.domain import (
    AddComponentArgs,
    AddEpicArgs,
    AddTestSpecArgs,
    AddUserStoryArgs,
    DeleteComponentArgs,
    DeleteDecisionArgs,
    DeleteStoryArgs,
    DeleteTaskArgs,
    DeleteTestSpecArgs,
    ProposeTaskArgs,
    RecordConstraintArgs,
    RecordDecisionArgs,
    SetMvpScopeArgs,
    SetProblemStatementArgs,
    UpdateComponentArgs,
    UpdateDecisionArgs,
    UpdateTaskArgs,
    UpdateTestSpecArgs,
    UpdateUserStoryArgs,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arg_model: Type[BaseModel]
    handler_name: str
    phases: frozenset[str]
    project_scoped: bool = True

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arg_model.model_json_schema(),
            },
        }

    async def invoke(self, project_id: str, tool_input: dict, svc) -> str:
        args = self.arg_model(**tool_input)
        handler = getattr(svc, self.handler_name)
        if self.project_scoped:
            return await handler(project_id, args)
        return await handler(args)


ALL_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        "set_problem_statement",
        "Record the core problem statement for this project.",
        SetProblemStatementArgs,
        "set_problem_statement",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "set_mvp_scope",
        "Persist the stories that belong in the MVP and the rationale for the cut.",
        SetMvpScopeArgs,
        "set_mvp_scope",
        frozenset({"pm"}),
    ),
    ToolDefinition(
        "add_epic",
        "Group related user stories under a named epic.",
        AddEpicArgs,
        "add_epic",
        frozenset({"pm"}),
    ),
    ToolDefinition(
        "add_user_story",
        "Capture a user story discovered in the conversation.",
        AddUserStoryArgs,
        "add_user_story",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "update_user_story",
        "Revise an existing user story.",
        UpdateUserStoryArgs,
        "update_user_story",
        frozenset({"ba", "pm", "review"}),
    ),
    ToolDefinition(
        "record_constraint",
        "Record a technical, business, or time constraint.",
        RecordConstraintArgs,
        "record_constraint",
        frozenset({"ba", "architect", "pm"}),
    ),
    ToolDefinition(
        "add_component",
        "Define an architectural component.",
        AddComponentArgs,
        "add_component",
        frozenset({"architect"}),
    ),
    ToolDefinition(
        "record_decision",
        "Record an Architecture Decision Record (ADR).",
        RecordDecisionArgs,
        "record_decision",
        frozenset({"architect"}),
    ),
    ToolDefinition(
        "add_test_spec",
        "Write a TDD test specification in Given/When/Then format.",
        AddTestSpecArgs,
        "add_test_spec",
        frozenset({"tdd"}),
    ),
    ToolDefinition(
        "propose_task",
        "Propose an atomized implementation task for the agent team.",
        ProposeTaskArgs,
        "propose_task",
        frozenset({"tdd"}),
    ),
    ToolDefinition(
        "delete_story",
        "Delete a duplicate or low-quality user story.",
        DeleteStoryArgs,
        "delete_story",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "update_component",
        "Polish a component's name or responsibility description.",
        UpdateComponentArgs,
        "update_component",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "delete_component",
        "Delete a duplicate or redundant architectural component.",
        DeleteComponentArgs,
        "delete_component",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "update_decision",
        "Polish an architecture decision's title, context, or decision text.",
        UpdateDecisionArgs,
        "update_decision",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "delete_decision",
        "Delete a duplicate or redundant architecture decision.",
        DeleteDecisionArgs,
        "delete_decision",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "update_test_spec",
        "Polish a test specification's description or Given/When/Then fields.",
        UpdateTestSpecArgs,
        "update_test_spec",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "delete_test_spec",
        "Delete a duplicate or redundant test specification.",
        DeleteTestSpecArgs,
        "delete_test_spec",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "update_task",
        "Polish a task's title, description, or complexity.",
        UpdateTaskArgs,
        "update_task",
        frozenset({"review"}),
    ),
    ToolDefinition(
        "delete_task",
        "Delete a duplicate or redundant implementation task.",
        DeleteTaskArgs,
        "delete_task",
        frozenset({"review"}),
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}

# Aliases for tool names the LLM commonly hallucinates. Maps the hallucinated
# name to the canonical one so the call still executes.
TOOL_ALIASES: dict[str, str] = {
    "add_task": "propose_task",
    "create_task": "propose_task",
    "add_decision": "record_decision",
    "create_decision": "record_decision",
    "add_constraint": "record_constraint",
    "create_constraint": "record_constraint",
    "create_component": "add_component",
    "create_epic": "add_epic",
    "add_story": "add_user_story",
    "create_story": "add_user_story",
    "create_user_story": "add_user_story",
    "add_test": "add_test_spec",
    "create_test_spec": "add_test_spec",
    "set_problem": "set_problem_statement",
    "set_mvp": "set_mvp_scope",
}


def get_phase_tools(phase: str) -> list[dict]:
    return [tool.schema() for tool in ALL_TOOLS if phase in tool.phases]


def get_phase_tool_names(phase: str) -> set[str]:
    return {tool.name for tool in ALL_TOOLS if phase in tool.phases}


async def dispatch_tool(project_id: str, tool_name: str, tool_input: dict, svc) -> str:
    resolved = TOOL_ALIASES.get(tool_name, tool_name)
    tool = TOOLS_BY_NAME.get(resolved)
    if not tool:
        log.warning("Unknown tool call: %s (no alias match)", tool_name)
        return f"Unknown tool: {tool_name}"
    if resolved != tool_name:
        log.info("Resolved tool alias %s -> %s", tool_name, resolved)
    try:
        return await tool.invoke(project_id, tool_input, svc)
    except Exception as exc:
        log.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        # Roll back the session so the next tool call in the same stream can proceed.
        # Without this, a failed flush leaves the session in PendingRollbackError state.
        try:
            await svc.db.rollback()
        except Exception:
            pass
        return f"Error: {exc}"


def parse_tool_arguments(raw_arguments: str) -> dict:
    if not raw_arguments:
        return {}
    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {}
