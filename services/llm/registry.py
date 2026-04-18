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
        project_scoped=False,
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
        project_scoped=False,
    ),
    ToolDefinition(
        "update_component",
        "Polish a component's name or responsibility description.",
        UpdateComponentArgs,
        "update_component",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "delete_component",
        "Delete a duplicate or redundant architectural component.",
        DeleteComponentArgs,
        "delete_component",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "update_decision",
        "Polish an architecture decision's title, context, or decision text.",
        UpdateDecisionArgs,
        "update_decision",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "delete_decision",
        "Delete a duplicate or redundant architecture decision.",
        DeleteDecisionArgs,
        "delete_decision",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "update_test_spec",
        "Polish a test specification's description or Given/When/Then fields.",
        UpdateTestSpecArgs,
        "update_test_spec",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "delete_test_spec",
        "Delete a duplicate or redundant test specification.",
        DeleteTestSpecArgs,
        "delete_test_spec",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "update_task",
        "Polish a task's title, description, or complexity.",
        UpdateTaskArgs,
        "update_task",
        frozenset({"review"}),
        project_scoped=False,
    ),
    ToolDefinition(
        "delete_task",
        "Delete a duplicate or redundant implementation task.",
        DeleteTaskArgs,
        "delete_task",
        frozenset({"review"}),
        project_scoped=False,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in ALL_TOOLS}


def get_phase_tools(phase: str) -> list[dict]:
    return [tool.schema() for tool in ALL_TOOLS if phase in tool.phases]


def get_phase_tool_names(phase: str) -> set[str]:
    return {tool.name for tool in ALL_TOOLS if phase in tool.phases}


async def dispatch_tool(project_id: str, tool_name: str, tool_input: dict, svc) -> str:
    tool = TOOLS_BY_NAME.get(tool_name)
    if not tool:
        return f"Unknown tool: {tool_name}"
    try:
        return await tool.invoke(project_id, tool_input, svc)
    except Exception as exc:
        log.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
        return f"Error: {exc}"


def parse_tool_arguments(raw_arguments: str) -> dict:
    if not raw_arguments:
        return {}
    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {}
