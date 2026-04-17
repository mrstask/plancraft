"""Claude API integration — streaming, tool use, knowledge extraction."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import (
    KnowledgeSnapshot,
    AddUserStoryArgs, UpdateUserStoryArgs, AddEpicArgs, RecordConstraintArgs,
    AddComponentArgs, RecordDecisionArgs, AddTestSpecArgs, ProposeTaskArgs,
    SetProblemStatementArgs, SetMvpScopeArgs,
)
from roles import BusinessAnalystRole, ProductManagerRole, ArchitectRole, TDDTesterRole
from services.knowledge import KnowledgeService

log = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

# ---------------------------------------------------------------------------
# Tool definitions (sent to Claude)
# ---------------------------------------------------------------------------

KNOWLEDGE_TOOLS: list[dict] = [
    {
        "name": "set_problem_statement",
        "description": "Record the core problem statement for this project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "statement": {"type": "string", "description": "Concise problem statement (2-4 sentences)"},
            },
            "required": ["statement"],
        },
    },
    {
        "name": "add_epic",
        "description": "Group related user stories under a named epic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "add_user_story",
        "description": "Capture a user story discovered in the conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_a": {"type": "string"},
                "i_want": {"type": "string"},
                "so_that": {"type": "string"},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "priority": {"type": "string", "enum": ["must", "should", "could", "wont"]},
                "epic_id": {"type": "string", "description": "Existing epic ID, if applicable"},
            },
            "required": ["as_a", "i_want", "so_that"],
        },
    },
    {
        "name": "update_user_story",
        "description": "Revise an existing user story.",
        "input_schema": {
            "type": "object",
            "properties": {
                "story_id": {"type": "string"},
                "as_a": {"type": "string"},
                "i_want": {"type": "string"},
                "so_that": {"type": "string"},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "priority": {"type": "string", "enum": ["must", "should", "could", "wont"]},
            },
            "required": ["story_id"],
        },
    },
    {
        "name": "record_constraint",
        "description": "Record a technical, business, or time constraint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["technical", "business", "time"]},
                "description": {"type": "string"},
            },
            "required": ["type", "description"],
        },
    },
    {
        "name": "add_component",
        "description": "Define an architectural component.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "responsibility": {"type": "string"},
                "component_type": {"type": "string"},
                "file_paths": {"type": "array", "items": {"type": "string"}},
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Component IDs this component depends on",
                },
            },
            "required": ["name", "responsibility"],
        },
    },
    {
        "name": "record_decision",
        "description": "Record an Architecture Decision Record (ADR).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "context": {"type": "string"},
                "decision": {"type": "string"},
                "consequences_positive": {"type": "array", "items": {"type": "string"}},
                "consequences_negative": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "decision"],
        },
    },
    {
        "name": "add_test_spec",
        "description": "Write a TDD test specification in Given/When/Then format.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "test_type": {"type": "string", "enum": ["unit", "integration", "e2e"]},
                "story_id": {"type": "string"},
                "component_id": {"type": "string"},
                "given_context": {"type": "string"},
                "when_action": {"type": "string"},
                "then_expectation": {"type": "string"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "propose_task",
        "description": "Propose an atomized implementation task for the agent team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "complexity": {"type": "string", "enum": ["trivial", "small", "medium", "large"]},
                "file_paths": {"type": "array", "items": {"type": "string"}},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs this task depends on",
                },
                "story_ids": {"type": "array", "items": {"type": "string"}},
                "test_spec_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "description"],
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(snapshot: KnowledgeSnapshot) -> str:
    roles = [
        BusinessAnalystRole(),
        ProductManagerRole(),
        ArchitectRole(),
        TDDTesterRole(),
    ]
    role_fragments = "\n".join(r.system_prompt_fragment for r in roles)

    return f"""You are a collaborative software planning assistant. You help teams \
design and plan software projects through natural conversation.

You fluidly embody four roles based on what the conversation needs:
{role_fragments}

## Behaviour
- Shift naturally between roles as the conversation evolves — don't announce role changes
- Ask one focused question at a time; don't overwhelm with a list of questions
- Push back on vague requirements and untestable acceptance criteria
- When you learn something structured (a story, component, decision, test spec), \
call the appropriate tool immediately — don't ask permission first. \
You can briefly mention "I've noted that as..." in your response.
- Keep responses concise and conversational. This is a dialog, not a document.

## Current Project State
{snapshot.to_context_string()}
"""


# ---------------------------------------------------------------------------
# Streaming chat with tool dispatch
# ---------------------------------------------------------------------------

async def stream_response(
    project_id: str,
    messages: list[dict],
    db: AsyncSession,
) -> AsyncIterator[dict]:
    """
    Stream Claude's response and dispatch tool calls to the knowledge model.
    Yields dicts:
      {"type": "text", "content": "..."}          — text token
      {"type": "tool_used", "name": "...", "result": "..."}  — tool executed
      {"type": "done", "persona": "..."}           — stream complete
    """
    knowledge_svc = KnowledgeService(db)
    snapshot = await knowledge_svc.get_snapshot(project_id)
    system_prompt = build_system_prompt(snapshot)

    full_text = ""
    tool_calls_made = []

    async with client.messages.stream(
        model=settings.claude_model,
        max_tokens=settings.max_tokens,
        system=system_prompt,
        tools=KNOWLEDGE_TOOLS,
        messages=messages,
    ) as stream:
        async for event in stream:
            if hasattr(event, "type"):
                if event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        full_text += delta.text
                        yield {"type": "text", "content": delta.text}

                elif event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        # Tool call incoming — accumulate and dispatch after stream
                        pass

        # After stream ends, check for tool calls in the final message
        final_message = await stream.get_final_message()

    # Dispatch tool calls
    for block in final_message.content:
        if block.type == "tool_use":
            result = await _dispatch_tool(project_id, block.name, block.input, knowledge_svc)
            tool_calls_made.append({"name": block.name, "result": result})
            yield {"type": "tool_used", "name": block.name, "result": result}

    # Detect active persona from content
    persona = _detect_persona(full_text)
    yield {"type": "done", "persona": persona, "tool_calls": tool_calls_made}


async def _dispatch_tool(
    project_id: str,
    tool_name: str,
    tool_input: dict,
    svc: KnowledgeService,
) -> str:
    """Dispatch a Claude tool call to the knowledge service."""
    try:
        match tool_name:
            case "set_problem_statement":
                return await svc.set_problem_statement(project_id, SetProblemStatementArgs(**tool_input))
            case "add_epic":
                return await svc.add_epic(project_id, AddEpicArgs(**tool_input))
            case "add_user_story":
                return await svc.add_user_story(project_id, AddUserStoryArgs(**tool_input))
            case "update_user_story":
                return await svc.update_user_story(UpdateUserStoryArgs(**tool_input))
            case "record_constraint":
                return await svc.record_constraint(project_id, RecordConstraintArgs(**tool_input))
            case "add_component":
                return await svc.add_component(project_id, AddComponentArgs(**tool_input))
            case "record_decision":
                return await svc.record_decision(project_id, RecordDecisionArgs(**tool_input))
            case "add_test_spec":
                return await svc.add_test_spec(project_id, AddTestSpecArgs(**tool_input))
            case "propose_task":
                return await svc.propose_task(project_id, ProposeTaskArgs(**tool_input))
            case _:
                return f"Unknown tool: {tool_name}"
    except Exception as e:
        log.error(f"Tool {tool_name} failed: {e}")
        return f"Error: {e}"


def _detect_persona(text: str) -> str:
    """Infer active role from response content for the UI badge."""
    text_lower = text.lower()
    from roles import BusinessAnalystRole, ProductManagerRole, ArchitectRole, TDDTesterRole
    scores = {
        "ba": sum(1 for kw in BusinessAnalystRole().trigger_keywords if kw in text_lower),
        "pm": sum(1 for kw in ProductManagerRole().trigger_keywords if kw in text_lower),
        "architect": sum(1 for kw in ArchitectRole().trigger_keywords if kw in text_lower),
        "tdd": sum(1 for kw in TDDTesterRole().trigger_keywords if kw in text_lower),
    }
    return max(scores, key=scores.get) if any(scores.values()) else "ba"
