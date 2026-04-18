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
    UpdateComponentArgs, UpdateDecisionArgs, UpdateTestSpecArgs, UpdateTaskArgs,
)
from roles import BusinessAnalystRole, ProductManagerRole, ArchitectRole, TDDTesterRole, ReviewerRole

# ---------------------------------------------------------------------------
# Phase → role + tool scope mapping
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    "ba":        BusinessAnalystRole,
    "pm":        ProductManagerRole,
    "architect": ArchitectRole,
    "tdd":       TDDTesterRole,
    "review":    ReviewerRole,
}

_PHASE_TOOL_NAMES: dict[str, set[str]] = {
    "ba":        {"set_problem_statement", "add_user_story", "update_user_story", "record_constraint"},
    "pm":        {"add_epic", "update_user_story"},
    "architect": {"add_component", "record_decision", "record_constraint"},
    "tdd":       {"add_test_spec", "propose_task"},
    "review":    {
        "delete_story",
        "update_component", "delete_component",
        "update_decision",  "delete_decision",
        "update_test_spec", "delete_test_spec",
        "update_task",      "delete_task",
    },
}


def _get_phase_tools(phase: str) -> list[dict]:
    names = _PHASE_TOOL_NAMES.get(phase, set())
    return [t for t in KNOWLEDGE_TOOLS if t["function"]["name"] in names]
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
    # ---- Review phase tools ------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "delete_story",
            "description": "Delete a duplicate or low-quality user story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "story_id": {"type": "string"},
                    "reason":   {"type": "string", "description": "Why this story is being removed"},
                },
                "required": ["story_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_component",
            "description": "Polish a component's name or responsibility description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component_id":    {"type": "string"},
                    "name":            {"type": "string"},
                    "responsibility":  {"type": "string"},
                    "component_type":  {"type": "string"},
                },
                "required": ["component_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_component",
            "description": "Delete a duplicate or redundant architectural component.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component_id": {"type": "string"},
                    "reason":       {"type": "string"},
                },
                "required": ["component_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_decision",
            "description": "Polish an architecture decision's title, context, or decision text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision_id": {"type": "string"},
                    "title":       {"type": "string"},
                    "context":     {"type": "string"},
                    "decision":    {"type": "string"},
                },
                "required": ["decision_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_decision",
            "description": "Delete a duplicate or redundant architecture decision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision_id": {"type": "string"},
                    "reason":      {"type": "string"},
                },
                "required": ["decision_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_test_spec",
            "description": "Polish a test specification's description or Given/When/Then fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spec_id":          {"type": "string"},
                    "description":      {"type": "string"},
                    "given_context":    {"type": "string"},
                    "when_action":      {"type": "string"},
                    "then_expectation": {"type": "string"},
                    "test_type": {
                        "type": "string",
                        "enum": ["unit", "integration", "e2e"],
                    },
                },
                "required": ["spec_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_test_spec",
            "description": "Delete a duplicate or redundant test specification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spec_id": {"type": "string"},
                    "reason":  {"type": "string"},
                },
                "required": ["spec_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Polish a task's title, description, or complexity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id":     {"type": "string"},
                    "title":       {"type": "string"},
                    "description": {"type": "string"},
                    "complexity": {
                        "type": "string",
                        "enum": ["trivial", "small", "medium", "large"],
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Delete a duplicate or redundant implementation task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "reason":  {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(
    snapshot: KnowledgeSnapshot,
    role_tab: str = "ba",
    full_context: str | None = None,
) -> str:
    role = _ROLE_MAP.get(role_tab, BusinessAnalystRole)()

    # Build tool-calling rules specific to this phase
    tool_rules = {
        "ba": (
            "- When you articulate or refine the problem statement → call set_problem_statement().\n"
            "- When you identify a user story → call add_user_story() immediately.\n"
            "- When you refine an existing story → call update_user_story().\n"
            "- When you note a constraint → call record_constraint().\n"
        ),
        "pm": (
            "- When you define or refine an epic → call add_epic().\n"
            "- When you update a story's priority or epic assignment → call update_user_story().\n"
        ),
        "architect": (
            "- When you propose a component → call add_component() immediately, one call per component.\n"
            "- When you make an architecture decision → call record_decision() immediately.\n"
            "- When you note a technical constraint → call record_constraint().\n"
        ),
        "tdd": (
            "- EVERY test spec you think of → call add_test_spec() in THIS response, right now.\n"
            "- EVERY implementation task → call propose_task() in THIS response.\n"
            "- A text description of a test spec is FORBIDDEN — tools only.\n"
            "- Cover ALL components visible in the project state — do not ask which to start with.\n"
            "- Minimum tool calls per response: one add_test_spec() per component or story in context.\n"
        ),
        "review": (
            "- When you find a duplicate artifact → call delete_* immediately.\n"
            "- When wording needs improvement → call update_* immediately.\n"
            "- Process ALL artifact categories (stories, components, decisions, specs, tasks) in ONE response.\n"
            "- Use the artifact IDs shown in the context — they are exact UUIDs you must copy precisely.\n"
        ),
    }.get(role_tab, "")

    return f"""You are a software planning assistant acting as {role.name} for this project.

{role.system_prompt_fragment}

## MANDATORY Tool-Calling Rules
You have tools to persist structured knowledge. These rules are NON-NEGOTIABLE:

{tool_rules}
Call tools IN THE SAME TURN you discuss the item — never in a future turn.
Do NOT describe an item in text without calling the corresponding tool.
You may briefly confirm after calling: "Saved ✓" or "Noted as a component."

## Behaviour
- Ask one focused question at a time
- Push back on vague requirements
- Keep responses concise and conversational — this is a dialog, not a document
- When you have enough material for this phase, suggest moving to the next one

## Current Project State
{full_context if full_context is not None else snapshot.to_context_string()}
"""


# ---------------------------------------------------------------------------
# Streaming chat with tool dispatch
# ---------------------------------------------------------------------------

async def stream_response(
    project_id: str,
    messages: list[dict],
    db: AsyncSession,
    role_tab: str = "ba",
) -> AsyncIterator[dict]:
    """
    Stream the LLM response and dispatch any tool calls to the knowledge model.

    Gemma4 wraps chain-of-thought in <think>…</think> tags at the start of
    its response. We split that out into separate chunk types so the UI can
    render thinking and reply content differently.

    Yields dicts:
      {"type": "thinking",  "content": "..."}   — inside <think>…</think>
      {"type": "text",      "content": "..."}   — visible reply
      {"type": "tool_used", "name": "...", "result": "..."}
      {"type": "done",      "persona": "...", "tool_calls": [...]}
    """
    knowledge_svc = KnowledgeService(db)
    snapshot = await knowledge_svc.get_snapshot(project_id)

    # Review phase gets ALL artifacts as context so the LLM can reference IDs
    full_context = None
    if role_tab == "review":
        full_context = await knowledge_svc.get_full_review_context(project_id)

    system_prompt = build_system_prompt(snapshot, role_tab, full_context=full_context)

    full_text_parts: list[str] = []
    pending_tool_calls: dict[int, dict] = {}

    # State machine for <think>…</think> detection.
    # Tokens arrive one at a time so the tag may span multiple chunks;
    # we keep a small look-ahead buffer to handle that edge case.
    in_thinking = False
    tag_buf = ""          # accumulates chars while we might be mid-tag

    OPEN_TAG  = "<think>"
    CLOSE_TAG = "</think>"
    MAX_BUF   = max(len(OPEN_TAG), len(CLOSE_TAG))

    async def _flush_tag_buf(force: bool = False):
        """Yield whatever is sitting in tag_buf as the current type.
        Called when we are sure the buffer is not part of a tag boundary."""
        nonlocal tag_buf, in_thinking
        if not tag_buf:
            return
        if not force:
            # Keep up to MAX_BUF-1 chars in case a tag starts at the tail
            safe = tag_buf[: max(0, len(tag_buf) - MAX_BUF + 1)]
            tag_buf = tag_buf[len(safe):]
        else:
            safe, tag_buf = tag_buf, ""
        if not safe:
            return
        if in_thinking:
            yield {"type": "thinking", "content": safe}
        else:
            full_text_parts.append(safe)
            yield {"type": "text", "content": safe}

    async def _process(raw: str):
        """Feed raw token text through the think-tag state machine."""
        nonlocal in_thinking, tag_buf
        tag_buf += raw

        # Process tag_buf until it's small enough to safely buffer
        while len(tag_buf) >= MAX_BUF:
            tag = OPEN_TAG if not in_thinking else CLOSE_TAG
            idx = tag_buf.find(tag)

            if idx == 0:
                # Tag starts right here — switch state, consume it
                in_thinking = not in_thinking
                tag_buf = tag_buf[len(tag):]
            elif idx > 0:
                # Emit everything before the tag, then loop
                head = tag_buf[:idx]
                tag_buf = tag_buf[idx:]
                if in_thinking:
                    yield {"type": "thinking", "content": head}
                else:
                    full_text_parts.append(head)
                    yield {"type": "text", "content": head}
            else:
                # Tag not found — safe to emit up to MAX_BUF-1 chars
                safe = tag_buf[: len(tag_buf) - MAX_BUF + 1]
                tag_buf = tag_buf[len(safe):]
                if in_thinking:
                    yield {"type": "thinking", "content": safe}
                else:
                    full_text_parts.append(safe)
                    yield {"type": "text", "content": safe}

    phase_tools = _get_phase_tools(role_tab)
    # TDD and Review use the larger model and force at least one tool call per turn.
    model_name = settings.tdd_model if role_tab in ("tdd", "review") else settings.ollama_model
    log.info(f"[{role_tab}] Using model: {model_name}")
    tool_choice = "required" if role_tab in ("tdd", "review") else "auto"
    stream = await client.chat.completions.create(
        model=model_name,
        max_tokens=settings.max_tokens,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        tools=phase_tools,
        tool_choice=tool_choice,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        # --- Text tokens (route through think-tag state machine) ---
        if delta.content:
            async for item in _process(delta.content):
                yield item

        # --- Tool call fragments ---
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

    # Flush any remaining buffered content
    async for item in _flush_tag_buf(force=True):
        yield item

    # --- Dispatch completed tool calls ---
    tool_calls_made = []
    log.info(f"[{role_tab}] Stream ended — {len(pending_tool_calls)} tool call(s) pending, {len(full_text_parts)} text chunk(s)")
    for tc in pending_tool_calls.values():
        if not tc["name"]:
            continue
        try:
            args = json.loads(tc["args_str"]) if tc["args_str"] else {}
        except json.JSONDecodeError:
            log.warning(f"Could not parse tool args for {tc['name']}: {tc['args_str']!r}")
            args = {}

        log.info(f"[{role_tab}] Dispatching tool: {tc['name']} args={list(args.keys())}")
        result = await _dispatch_tool(project_id, tc["name"], args, knowledge_svc)
        log.info(f"[{role_tab}] Tool result: {result}")
        tool_calls_made.append({"name": tc["name"], "result": result})
        yield {"type": "tool_used", "name": tc["name"], "result": result}

    # --- Fallback extraction pass ---
    # If the model described structured items in text but called zero tools,
    # send a second non-streaming call to extract and persist them.
    # For TDD phase the bar is lower: any response without tool calls is suspicious.
    full_text = "".join(full_text_parts)
    full_text_preview = full_text[:120].replace("\n", " ")
    should_extract = (
        not tool_calls_made
        and (_should_extract(full_text, role_tab=role_tab))
    )
    if not tool_calls_made:
        log.warning(f"[{role_tab}] Zero tool calls made. Text preview: {full_text_preview!r}")
    if should_extract:
        log.info(f"[{role_tab}] Running fallback extraction pass (text len={len(full_text)})")
        async for item in _extraction_pass(project_id, messages, full_text, knowledge_svc, role_tab):
            yield item
            if item["type"] == "tool_used":
                tool_calls_made.append({"name": item["name"], "result": item["result"]})

    persona = _detect_persona(full_text)
    yield {"type": "done", "persona": persona, "tool_calls": tool_calls_made}


# ---------------------------------------------------------------------------
# Fallback extraction helpers
# ---------------------------------------------------------------------------

# Keywords that suggest structured data was discussed but possibly not saved
_EXTRACTION_SIGNALS = [
    "component", "module", "service", "layer",
    "decision", "adr", "architecture decision",
    "user story", "as a user", "acceptance criteria",
    "test spec", "given", "when", "then",
    "epic",
]


def _should_extract(text: str, role_tab: str = "ba") -> bool:
    """Return True if the response contains structured items that should be saved."""
    t = text.lower()
    if role_tab == "tdd":
        # Any non-empty TDD response that didn't call tools needs extraction —
        # the model almost certainly described specs in prose instead of calling tools.
        return len(t.strip()) > 50
    return sum(1 for kw in _EXTRACTION_SIGNALS if kw in t) >= 2


async def _extraction_pass(
    project_id: str,
    original_messages: list[dict],
    assistant_reply: str,
    knowledge_svc: KnowledgeService,
    role_tab: str = "ba",
) -> AsyncIterator[dict]:
    """
    Second-pass, non-streaming call.  We append the assistant's reply to the
    conversation and ask the model to call the right tools to persist whatever
    structured data it described.  This is a silent background step — it does
    not emit any text tokens, only tool_used events.
    """
    if role_tab == "tdd":
        extraction_prompt = (
            "Your previous reply described test specifications and tasks in text instead of saving them. "
            "You MUST now call the tools to save everything you described:\n"
            "• add_test_spec() for EVERY test scenario you mentioned (one call per scenario)\n"
            "• propose_task() for EVERY implementation task you mentioned\n"
            "Use the Given/When/Then details from your reply as the tool arguments. "
            "Do NOT write any text — only make tool calls. Start immediately."
        )
    else:
        extraction_prompt = (
            "Looking back at your previous reply, please call the appropriate tools "
            "to save every item you described:\n"
            "• add_component() for each component or module\n"
            "• record_decision() for each architectural decision\n"
            "• add_user_story() for each user story\n"
            "• add_test_spec() for each test specification\n"
            "• add_epic() for each epic\n"
            "Call one tool per item. Do not write any text — only make tool calls."
        )
    extraction_messages = (
        [{"role": "system", "content": (
            "You are a data-extraction assistant. Your ONLY job is to call the "
            "provided tools to persist structured data. Do not write any prose."
        )}]
        + original_messages
        + [
            {"role": "assistant", "content": assistant_reply},
            {"role": "user",      "content": extraction_prompt},
        ]
    )

    extraction_model = settings.tdd_model if role_tab in ("tdd", "review") else settings.ollama_model
    try:
        resp = await client.chat.completions.create(
            model=extraction_model,
            max_tokens=1024,
            messages=extraction_messages,
            tools=_get_phase_tools(role_tab),
            stream=False,
        )
    except Exception as e:
        log.warning(f"Extraction pass failed: {e}")
        return

    message = resp.choices[0].message if resp.choices else None
    if not message or not message.tool_calls:
        log.warning(f"[{role_tab}] Extraction pass: model returned NO tool calls. finish_reason={resp.choices[0].finish_reason if resp.choices else 'n/a'}")
        if message and message.content:
            log.warning(f"[{role_tab}] Extraction pass text: {message.content[:200]!r}")
        return

    log.info(f"[{role_tab}] Extraction pass: {len(message.tool_calls)} tool call(s) returned")
    for tc in message.tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            log.warning(f"Extraction pass: bad JSON for {name}")
            continue
        result = await _dispatch_tool(project_id, name, args, knowledge_svc)
        log.info(f"Extraction pass saved: {name} → {result}")
        yield {"type": "tool_used", "name": name, "result": result}


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
            # --- Review phase tools ---
            case "delete_story":
                return await svc.delete_story(tool_input["story_id"])
            case "update_component":
                return await svc.update_component(UpdateComponentArgs(**tool_input))
            case "delete_component":
                return await svc.delete_component(tool_input["component_id"])
            case "update_decision":
                return await svc.update_decision(UpdateDecisionArgs(**tool_input))
            case "delete_decision":
                return await svc.delete_decision(tool_input["decision_id"])
            case "update_test_spec":
                return await svc.update_test_spec(UpdateTestSpecArgs(**tool_input))
            case "delete_test_spec":
                return await svc.delete_test_spec(tool_input["spec_id"])
            case "update_task":
                return await svc.update_task(UpdateTaskArgs(**tool_input))
            case "delete_task":
                return await svc.delete_task(tool_input["task_id"])
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
