"""Central registry for LLM tool schemas and dispatch."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from models.domain import (
    AddRoadmapItemArgs,
    AddBusinessRuleArgs,
    AddComponentArgs,
    AddDataEntityArgs,
    AddEpicArgs,
    AddFunctionalRequirementArgs,
    AddGlossaryTermArgs,
    AddInterfaceContractArgs,
    AddPersonaArgs,
    AddTestSpecArgs,
    AddTechStackEntryArgs,
    AddUserFlowArgs,
    AddUserStoryArgs,
    AnswerClarificationPointArgs,
    DeleteComponentArgs,
    DeleteInterfaceContractArgs,
    DeleteDecisionArgs,
    DeleteStoryArgs,
    DeleteTaskArgs,
    DeleteTestSpecArgs,
    ProposeTaskArgs,
    RecordConstraintArgs,
    RecordDecisionArgs,
    SetProjectMissionArgs,
    SetLlmInteractionModelArgs,
    SetMvpScopeArgs,
    SetProblemStatementArgs,
    SetVisionScopeArgs,
    UpdateComponentArgs,
    UpdateInterfaceContractArgs,
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
        "set_project_mission",
        "Create or update the project's mission statement, target users, and core problem.",
        SetProjectMissionArgs,
        "set_project_mission",
        frozenset({"founder"}),
    ),
    ToolDefinition(
        "add_roadmap_item",
        "Add or refine a roadmap milestone for the product.",
        AddRoadmapItemArgs,
        "add_roadmap_item",
        frozenset({"founder"}),
    ),
    ToolDefinition(
        "add_tech_stack_entry",
        "Add or refine a tech stack choice with rationale.",
        AddTechStackEntryArgs,
        "add_tech_stack_entry",
        frozenset({"founder"}),
    ),
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
    # BA extended tools
    ToolDefinition(
        "set_vision_scope",
        "Set or update Vision & Scope fields: business goals, success metrics, in-scope and out-of-scope items, target users.",
        SetVisionScopeArgs,
        "set_vision_scope",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_persona",
        "Define a user persona with role, goals, and pain points.",
        AddPersonaArgs,
        "add_persona",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_user_flow",
        "Capture an end-to-end user flow with ordered steps.",
        AddUserFlowArgs,
        "add_user_flow",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_business_rule",
        "Record a business rule that constrains system behavior.",
        AddBusinessRuleArgs,
        "add_business_rule",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_data_entity",
        "Define a conceptual data entity with attributes and relationships.",
        AddDataEntityArgs,
        "add_data_entity",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_functional_requirement",
        "Capture a functional requirement with inputs, outputs, and links to user stories.",
        AddFunctionalRequirementArgs,
        "add_functional_requirement",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "add_glossary_term",
        "Add or update a domain term definition in the project glossary.",
        AddGlossaryTermArgs,
        "add_glossary_term",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "set_llm_interaction_model",
        "Define how the LLM component behaves: role, interaction pattern, memory strategy, error handling.",
        SetLlmInteractionModelArgs,
        "set_llm_interaction_model",
        frozenset({"ba"}),
    ),
    ToolDefinition(
        "answer_clarification_point",
        "Mark a clarification point as answered or skipped and store the canonical answer.",
        AnswerClarificationPointArgs,
        "answer_clarification_point",
        frozenset({"ba"}),
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
        "add_interface_contract",
        "Record or refine an interface/API/event contract for a component boundary.",
        AddInterfaceContractArgs,
        "add_interface_contract",
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
        "update_interface_contract",
        "Polish an interface contract's component link, kind, name, or markdown body.",
        UpdateInterfaceContractArgs,
        "update_interface_contract",
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
        "delete_interface_contract",
        "Delete a duplicate or redundant interface contract.",
        DeleteInterfaceContractArgs,
        "delete_interface_contract",
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
    "set_mission": "set_project_mission",
    "create_mission": "set_project_mission",
    "add_mission": "set_project_mission",
    "add_roadmap": "add_roadmap_item",
    "create_roadmap_item": "add_roadmap_item",
    "add_stack_entry": "add_tech_stack_entry",
    "create_stack_entry": "add_tech_stack_entry",
    "set_tech_stack": "add_tech_stack_entry",
    "add_task": "propose_task",
    "create_task": "propose_task",
    "add_decision": "record_decision",
    "create_decision": "record_decision",
    "record_contract": "add_interface_contract",
    "create_contract": "add_interface_contract",
    "add_contract": "add_interface_contract",
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
    # BA extended aliases
    "set_scope": "set_vision_scope",
    "set_vision": "set_vision_scope",
    "create_persona": "add_persona",
    "add_flow": "add_user_flow",
    "create_flow": "add_user_flow",
    "add_rule": "add_business_rule",
    "create_business_rule": "add_business_rule",
    "add_entity": "add_data_entity",
    "create_entity": "add_data_entity",
    "add_fr": "add_functional_requirement",
    "create_fr": "add_functional_requirement",
    "add_requirement": "add_functional_requirement",
    "add_term": "add_glossary_term",
    "add_glossary": "add_glossary_term",
    "set_llm_model": "set_llm_interaction_model",
    "answer_clarification": "answer_clarification_point",
    "mark_clarification": "answer_clarification_point",
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
