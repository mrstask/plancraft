"""Streaming chat orchestration for the planning assistant."""
from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from roles import (
    ArchitectRole,
    BusinessAnalystRole,
    FounderRole,
    ProductManagerRole,
    TDDTesterRole,
)
from services.knowledge import KnowledgeService
from .prompts import build_system_prompt
from .registry import TOOL_ALIASES, dispatch_tool, get_phase_tools, parse_tool_arguments

log = logging.getLogger(__name__)

client = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")

EXTRACTION_SIGNALS = [
    "mission", "roadmap", "tech stack", "stack",
    "component", "module", "service", "layer",
    "decision", "adr", "architecture decision",
    "user story", "as a user", "acceptance criteria",
    "test spec", "given", "when", "then",
    "epic", "mvp",
]

# Names the model sometimes writes as pseudo-function-calls in prose
# instead of firing the real tool_calls API. When we see these, we force
# an extraction pass even if the conversational signals are sparse.
PSEUDO_CALL_NAMES = (
    "set_project_mission", "add_roadmap_item", "add_tech_stack_entry",
    "add_epic", "add_user_story", "update_user_story",
    "add_component", "add_test_spec", "propose_task",
    "record_decision", "record_constraint",
    "set_problem_statement", "set_mvp_scope",
)


def _has_pseudo_tool_call(text: str) -> bool:
    """Detect `tool_name(` or `tool_name{` patterns the model writes in prose."""
    lowered = text.lower()
    return any(f"{name}(" in lowered or f"{name}{{" in lowered for name in PSEUDO_CALL_NAMES)


def should_extract(text: str, role_tab: str = "ba") -> bool:
    t = text.lower()
    if role_tab == "tdd":
        return len(t.strip()) > 50
    if _has_pseudo_tool_call(t):
        return True
    return sum(1 for kw in EXTRACTION_SIGNALS if kw in t) >= 2


async def extraction_pass(
    project_id: str,
    original_messages: list[dict],
    assistant_reply: str,
    knowledge_svc: KnowledgeService,
    role_tab: str = "ba",
) -> AsyncIterator[dict]:
    if role_tab == "tdd":
        extraction_prompt = (
            "Your previous reply described test specifications and tasks in text instead of saving them. "
            "Call add_test_spec() for every scenario and propose_task() for every implementation task. "
            "Do not write any text."
        )
    elif role_tab == "founder":
        extraction_prompt = (
            "Looking back at your previous reply, save the mission, roadmap items, and tech stack choices "
            "you described. Call tools only and do not write prose."
        )
    elif role_tab == "pm":
        extraction_prompt = (
            "Looking back at your previous reply, save every epic, user-story update, MVP cut, and constraint "
            "you described. Call tools only and do not write prose."
        )
    else:
        extraction_prompt = (
            "Looking back at your previous reply, call the appropriate tools to save every artifact you described. "
            "Do not write any text."
        )

    extraction_messages = (
        [{"role": "system", "content": (
            "You are a data-extraction assistant. Your only job is to call the provided tools "
            "to persist structured data. Do not write prose."
        )}]
        + original_messages
        + [
            {"role": "assistant", "content": assistant_reply},
            {"role": "user", "content": extraction_prompt},
        ]
    )

    # Always use the tool-calling-optimized model for extraction. The lighter
    # ollama_model tends to emit pseudo-call syntax in prose instead of firing
    # the real tool_calls API, which is exactly the failure mode this pass exists to recover from.
    extraction_model = settings.ollama_model
    try:
        resp = await client.chat.completions.create(
            model=extraction_model,
            max_tokens=1024,
            messages=extraction_messages,
            tools=get_phase_tools(role_tab),
            tool_choice="required",
            stream=False,
        )
    except Exception as exc:
        log.warning("Extraction pass failed: %s", exc)
        return

    message = resp.choices[0].message if resp.choices else None
    if not message or not message.tool_calls:
        log.warning(
            "[%s] Extraction pass: model returned no tool calls. finish_reason=%s",
            role_tab,
            resp.choices[0].finish_reason if resp.choices else "n/a",
        )
        return

    for tc in message.tool_calls:
        args = parse_tool_arguments(tc.function.arguments or "{}")
        result = await dispatch_tool(project_id, tc.function.name, args, knowledge_svc)
        resolved_name = TOOL_ALIASES.get(tc.function.name, tc.function.name)
        yield {"type": "tool_used", "name": resolved_name, "result": result}


async def _propose_tasks_pass(
    project_id: str,
    original_messages: list[dict],
    knowledge_svc: KnowledgeService,
) -> AsyncIterator[dict]:
    """Second pass for TDD phase: force propose_task calls once specs are saved.

    The TDD model often exhausts its response budget on add_test_spec calls and
    never gets to propose_task. This follow-up pass loads fresh TDD context
    (now including the just-saved specs) and restricts the tool set to
    propose_task with tool_choice="required".
    """
    try:
        tdd_context = await knowledge_svc.get_tdd_context(project_id)
    except Exception as exc:
        log.warning("Tasks pass: could not build TDD context: %s", exc)
        tdd_context = ""

    system_msg = (
        "You are a TDD tester proposing atomic implementation tasks. "
        "Call propose_task() for EVERY distinct unit of work needed to build the MVP. "
        "Cover: each component's implementation, each test spec's scaffolding, "
        "integration wiring, and any infrastructure setup. "
        "One propose_task call per task. No prose. No other tools.\n\n"
        f"## Current Project State\n{tdd_context}"
    )
    user_msg = (
        "Propose every implementation task for the MVP right now. "
        "Call propose_task() for each one. Do not write any text."
    )

    tools = [t for t in get_phase_tools("tdd") if t["function"]["name"] == "propose_task"]

    try:
        resp = await client.chat.completions.create(
            model=settings.ollama_model,
            max_tokens=settings.max_tokens,
            messages=(
                [{"role": "system", "content": system_msg}]
                + original_messages
                + [{"role": "user", "content": user_msg}]
            ),
            tools=tools,
            tool_choice="required",
            stream=False,
        )
    except Exception as exc:
        log.warning("Tasks pass failed: %s", exc)
        return

    message = resp.choices[0].message if resp.choices else None
    if not message or not message.tool_calls:
        log.warning("Tasks pass produced no tool calls")
        return

    for tc in message.tool_calls:
        args = parse_tool_arguments(tc.function.arguments or "{}")
        result = await dispatch_tool(project_id, tc.function.name, args, knowledge_svc)
        resolved_name = TOOL_ALIASES.get(tc.function.name, tc.function.name)
        yield {"type": "tool_used", "name": resolved_name, "result": result}


def detect_persona(text: str) -> str:
    """Infer the active role from response content for the UI badge."""
    text_lower = text.lower()
    scores = {
        "founder": sum(1 for kw in FounderRole().trigger_keywords if kw in text_lower),
        "ba": sum(1 for kw in BusinessAnalystRole().trigger_keywords if kw in text_lower),
        "pm": sum(1 for kw in ProductManagerRole().trigger_keywords if kw in text_lower),
        "architect": sum(1 for kw in ArchitectRole().trigger_keywords if kw in text_lower),
        "tdd": sum(1 for kw in TDDTesterRole().trigger_keywords if kw in text_lower),
    }
    return max(scores, key=scores.get) if any(scores.values()) else "founder"


async def build_system_prompt_for(
    project_id: str,
    db: AsyncSession,
    role_tab: str = "ba",
    feature_id: str | None = None,
) -> str:
    """Assemble the exact system prompt that stream_response would send.

    Extracted so the context-usage endpoint can count tokens without invoking
    the model. Kept in sync with stream_response's prep block.
    """
    knowledge_svc = KnowledgeService(db, feature_id=feature_id)
    snapshot = await knowledge_svc.get_snapshot(project_id)

    full_context = None
    if role_tab == "founder":
        full_context = await knowledge_svc.get_founder_context(project_id)
    elif role_tab == "ba" and feature_id:
        full_context = await knowledge_svc.get_ba_context(project_id)
    elif role_tab == "pm":
        full_context = await knowledge_svc.get_pm_context(project_id)
    elif role_tab == "architect" and feature_id:
        full_context = await knowledge_svc.get_architect_context(project_id)
    elif role_tab == "tdd":
        full_context = await knowledge_svc.get_tdd_context(project_id)
    elif role_tab == "review":
        full_context = await knowledge_svc.get_full_review_context(project_id)

    return build_system_prompt(snapshot, role_tab, full_context=full_context)


async def stream_response(
    project_id: str,
    messages: list[dict],
    db: AsyncSession,
    role_tab: str = "ba",
    feature_id: str | None = None,
) -> AsyncIterator[dict]:
    knowledge_svc = KnowledgeService(db, feature_id=feature_id)
    system_prompt = await build_system_prompt_for(project_id, db, role_tab, feature_id)

    full_text_parts: list[str] = []
    pending_tool_calls: dict[int, dict] = {}

    in_thinking = False
    tag_buf = ""
    open_tag = "<think>"
    close_tag = "</think>"
    max_buf = max(len(open_tag), len(close_tag))

    async def flush_tag_buf(force: bool = False):
        nonlocal tag_buf, in_thinking
        if not tag_buf:
            return
        if not force:
            safe = tag_buf[: max(0, len(tag_buf) - max_buf + 1)]
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

    async def process_token(raw: str):
        nonlocal in_thinking, tag_buf
        tag_buf += raw

        while len(tag_buf) >= max_buf:
            tag = open_tag if not in_thinking else close_tag
            idx = tag_buf.find(tag)

            if idx == 0:
                in_thinking = not in_thinking
                tag_buf = tag_buf[len(tag):]
            elif idx > 0:
                head = tag_buf[:idx]
                tag_buf = tag_buf[idx:]
                if in_thinking:
                    yield {"type": "thinking", "content": head}
                else:
                    full_text_parts.append(head)
                    yield {"type": "text", "content": head}
            else:
                safe = tag_buf[: len(tag_buf) - max_buf + 1]
                tag_buf = tag_buf[len(safe):]
                if in_thinking:
                    yield {"type": "thinking", "content": safe}
                else:
                    full_text_parts.append(safe)
                    yield {"type": "text", "content": safe}

    model_name = settings.ollama_model
    tool_choice = "required" if role_tab in ("tdd", "review") else "auto"
    stream = await client.chat.completions.create(
        model=model_name,
        max_tokens=settings.max_tokens,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        tools=get_phase_tools(role_tab),
        tool_choice=tool_choice,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta is None:
            continue

        if delta.content:
            async for item in process_token(delta.content):
                yield item

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

    async for item in flush_tag_buf(force=True):
        yield item

    tool_calls_made = []
    for tc in pending_tool_calls.values():
        if not tc["name"]:
            continue
        args = parse_tool_arguments(tc["args_str"])
        result = await dispatch_tool(project_id, tc["name"], args, knowledge_svc)
        resolved_name = TOOL_ALIASES.get(tc["name"], tc["name"])
        tool_calls_made.append({"name": resolved_name, "result": result})
        yield {"type": "tool_used", "name": resolved_name, "result": result}

    full_text = "".join(full_text_parts)
    if not tool_calls_made and should_extract(full_text, role_tab=role_tab):
        async for item in extraction_pass(project_id, messages, full_text, knowledge_svc, role_tab):
            yield item
            if item["type"] == "tool_used":
                tool_calls_made.append({"name": item["name"], "result": item["result"]})

    # TDD phase follow-up: the model often saves test specs but stops before
    # proposing tasks. If that happened, force a second pass restricted to
    # propose_task so the task list actually gets populated.
    if role_tab == "tdd":
        saved_specs = [t for t in tool_calls_made if t["name"] == "add_test_spec"]
        saved_tasks = [t for t in tool_calls_made if t["name"] == "propose_task"]
        if saved_specs and not saved_tasks:
            async for item in _propose_tasks_pass(project_id, messages, knowledge_svc):
                yield item
                if item["type"] == "tool_used":
                    tool_calls_made.append({"name": item["name"], "result": item["result"]})

    # Safety net: if the model called tools but produced no visible text, run a
    # text-only continuation so the user always receives a reply. Only applies to
    # conversational phases (not tdd/review which are tool-output-only by design).
    if tool_calls_made and not full_text.strip() and role_tab not in ("tdd", "review"):
        saved_summary = ", ".join(t["name"].replace("_", " ") for t in tool_calls_made)
        continuation_hint = (
            f"You just called: {saved_summary}. "
            "Now write your conversational reply to the user's last message. No further tool calls."
        )
        continuation_messages = (
            [{"role": "system", "content": system_prompt + "\n\n" + continuation_hint}]
            + messages
        )
        try:
            cont_stream = await client.chat.completions.create(
                model=model_name,
                max_tokens=settings.max_tokens,
                messages=continuation_messages,
                stream=True,
            )
            async for chunk in cont_stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    async for item in process_token(delta.content):
                        full_text_parts.append(item["content"]) if item["type"] == "text" else None
                        yield item
            async for item in flush_tag_buf(force=True):
                if item["type"] == "text":
                    full_text_parts.append(item["content"])
                yield item
        except Exception as exc:
            log.warning("Continuation pass failed: %s", exc)

    full_text = "".join(full_text_parts)
    persona = detect_persona(full_text) if full_text.strip() else role_tab
    yield {"type": "done", "persona": persona, "tool_calls": tool_calls_made}
