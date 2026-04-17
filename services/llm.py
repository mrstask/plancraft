"""LLM service — Ollama backend via OpenAI-compatible API.

Uses the OpenAI Python client pointed at the local Ollama endpoint.
Tool calling follows the OpenAI function-calling protocol, which Ollama
exposes at /v1/chat/completions for models that support it (gemma4, llama3.x, etc.).
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI
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

# OpenAI client pointed at local Ollama — api_key value is ignored by Ollama
# but the client requires a non-empty string.
client = AsyncOpenAI(
    base_url=settings.ollama_base_url,
    api_key="ollama",
)

# ---------------------------------------------------------------------------
# Tool definitions — OpenAI function-calling format
# ---------------------------------------------------------------------------

KNOWLEDGE_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "set_problem_statement",
            "description": "Record the core problem statement for this project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "Concise problem statement (2-4 sentences)",
                    },
                },
                "required": ["statement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_epic",
            "description": "Group related user stories under a named epic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_user_story",
            "description": "Capture a user story discovered in the conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_a": {"type": "string"},
                    "i_want": {"type": "string"},
                    "so_that": {"type": "string"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["must", "should", "could", "wont"],
                    },
                    "epic_id": {
                        "type": "string",
                        "description": "Existing epic ID, if applicable",
                    },
                },
                "required": ["as_a", "i_want", "so_that"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_story",
            "description": "Revise an existing user story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "story_id": {"type": "string"},
                    "as_a": {"type": "string"},
                    "i_want": {"type": "string"},
                    "so_that": {"type": "string"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["must", "should", "could", "wont"],
                    },
                },
                "required": ["story_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_constraint",
            "description": "Record a technical, business, or time constraint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["technical", "business", "time"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["type", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_component",
            "description": "Define an architectural component.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "record_decision",
            "description": "Record an Architecture Decision Record (ADR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "context": {"type": "string"},
                    "decision": {"type": "string"},
                    "consequences_positive": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "consequences_negative": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "decision"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_test_spec",
            "description": "Write a TDD test specification in Given/When/Then format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "test_type": {
                        "type": "string",
                        "enum": ["unit", "integration", "e2e"],
                    },
                    "story_id": {"type": "string"},
                    "component_id": {"type": "string"},
                    "given_context": {"type": "string"},
                    "when_action": {"type": "string"},
                    "then_expectation": {"type": "string"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_task",
            "description": "Propose an atomized implementation task for the agent team.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "complexity": {
                        "type": "string",
                        "enum": ["trivial", "small", "medium", "large"],
                    },
                    "file_paths": {"type": "array", "items": {"type": "string"}},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
call the appropriate function immediately — don't ask permission first. \
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
    Stream the LLM response and dispatch any tool calls to the knowledge model.

    Yields dicts:
      {"type": "text",      "content": "..."}
      {"type": "tool_used", "name": "...", "result": "..."}
      {"type": "done",      "persona": "...", "tool_calls": [...]}
    """
    knowledge_svc = KnowledgeService(db)
    snapshot = await knowledge_svc.get_snapshot(project_id)
    system_prompt = build_system_prompt(snapshot)

    full_text_parts: list[str] = []
    # Accumulate streaming tool call fragments: {index: {id, name, args_str}}
    pending_tool_calls: dict[int, dict] = {}

    stream = await client.chat.completions.create(
        model=settings.ollama_model,
        max_tokens=settings.max_tokens,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        tools=KNOWLEDGE_TOOLS,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # --- Text tokens ---
        if delta.content:
            full_text_parts.append(delta.content)
            yield {"type": "text", "content": delta.content}

        # --- Tool call fragments (streamed piece by piece) ---
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in pending_tool_calls:
                    pending_tool_calls[idx] = {
                        "id": tc.id or "",
                        "name": tc.function.name or "" if tc.function else "",
                        "args_str": "",
                    }
                if tc.id:
                    pending_tool_calls[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        pending_tool_calls[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        pending_tool_calls[idx]["args_str"] += tc.function.arguments

    # --- Dispatch completed tool calls ---
    tool_calls_made = []
    for tc in pending_tool_calls.values():
        if not tc["name"]:
            continue
        try:
            args = json.loads(tc["args_str"]) if tc["args_str"] else {}
        except json.JSONDecodeError:
            log.warning(f"Could not parse tool args for {tc['name']}: {tc['args_str']!r}")
            args = {}

        result = await _dispatch_tool(project_id, tc["name"], args, knowledge_svc)
        tool_calls_made.append({"name": tc["name"], "result": result})
        yield {"type": "tool_used", "name": tc["name"], "result": result}

    persona = _detect_persona("".join(full_text_parts))
    yield {"type": "done", "persona": persona, "tool_calls": tool_calls_made}


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

async def _dispatch_tool(
    project_id: str,
    tool_name: str,
    tool_input: dict,
    svc: KnowledgeService,
) -> str:
    try:
        match tool_name:
            case "set_problem_statement":
                return await svc.set_problem_statement(
                    project_id, SetProblemStatementArgs(**tool_input)
                )
            case "add_epic":
                return await svc.add_epic(project_id, AddEpicArgs(**tool_input))
            case "add_user_story":
                return await svc.add_user_story(
                    project_id, AddUserStoryArgs(**tool_input)
                )
            case "update_user_story":
                return await svc.update_user_story(
                    UpdateUserStoryArgs(**tool_input)
                )
            case "record_constraint":
                return await svc.record_constraint(
                    project_id, RecordConstraintArgs(**tool_input)
                )
            case "add_component":
                return await svc.add_component(
                    project_id, AddComponentArgs(**tool_input)
                )
            case "record_decision":
                return await svc.record_decision(
                    project_id, RecordDecisionArgs(**tool_input)
                )
            case "add_test_spec":
                return await svc.add_test_spec(
                    project_id, AddTestSpecArgs(**tool_input)
                )
            case "propose_task":
                return await svc.propose_task(
                    project_id, ProposeTaskArgs(**tool_input)
                )
            case _:
                return f"Unknown tool: {tool_name}"
    except Exception as e:
        log.error(f"Tool {tool_name} failed: {e}", exc_info=True)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Persona detector
# ---------------------------------------------------------------------------

def _detect_persona(text: str) -> str:
    """Infer the active role from response content for the UI badge."""
    text_lower = text.lower()
    scores = {
        "ba":       sum(1 for kw in BusinessAnalystRole().trigger_keywords   if kw in text_lower),
        "pm":       sum(1 for kw in ProductManagerRole().trigger_keywords    if kw in text_lower),
        "architect":sum(1 for kw in ArchitectRole().trigger_keywords         if kw in text_lower),
        "tdd":      sum(1 for kw in TDDTesterRole().trigger_keywords         if kw in text_lower),
    }
    return max(scores, key=scores.get) if any(scores.values()) else "ba"
