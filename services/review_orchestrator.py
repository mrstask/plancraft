"""
Multi-pass review orchestrator.

Runs 6 focused LLM passes over the knowledge base:
  1. Stories
  2. Components
  3. Decisions
  4. Test Specs
  5. Tasks
  6. Holistic cross-category consistency check

Each pass gets only its own category as context — keeps the model focused and
avoids diluting attention across hundreds of artifacts at once.

The final holistic pass receives the full (now cleaned) knowledge base and
looks for cross-category issues: orphaned test specs, tasks without stories,
component names inconsistent with decision text, etc.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.knowledge import KnowledgeService
from services.llm import dispatch_tool, get_phase_tools

log = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")

# Tools available during review (same subset as the review phase)
_REVIEW_TOOLS = get_phase_tools("review")

# ---------------------------------------------------------------------------
# Per-category context builders
# ---------------------------------------------------------------------------

def _stories_context(stories) -> str:
    if not stories:
        return "No stories recorded."
    lines = [f"STORIES TO REVIEW ({len(stories)} total)\n"]
    for s in stories:
        lines.append(f"[{s.id}]")
        lines.append(f"  As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
        lines.append(f"  Priority: {s.priority}")
        if s.acceptance_criteria:
            for ac in s.acceptance_criteria:
                lines.append(f"  AC: {ac.criterion}")
        lines.append("")
    return "\n".join(lines)


def _components_context(components) -> str:
    if not components:
        return "No components recorded."
    lines = [f"COMPONENTS TO REVIEW ({len(components)} total)\n"]
    for c in components:
        lines.append(f"[{c.id}]")
        lines.append(f"  Name: {c.name}")
        lines.append(f"  Type: {c.component_type or '–'}")
        lines.append(f"  Responsibility: {c.responsibility}")
        lines.append("")
    return "\n".join(lines)


def _decisions_context(decisions) -> str:
    if not decisions:
        return "No architecture decisions recorded."
    lines = [f"ARCHITECTURE DECISIONS TO REVIEW ({len(decisions)} total)\n"]
    for d in decisions:
        lines.append(f"[{d.id}]")
        lines.append(f"  Title: {d.title}")
        lines.append(f"  Decision: {d.decision}")
        if d.context:
            lines.append(f"  Context: {d.context}")
        lines.append("")
    return "\n".join(lines)


def _specs_context(specs) -> str:
    if not specs:
        return "No test specs recorded."
    lines = [f"TEST SPECS TO REVIEW ({len(specs)} total)\n"]
    for sp in specs:
        lines.append(f"[{sp.id}]")
        lines.append(f"  Description: {sp.description}")
        lines.append(f"  Type: {sp.test_type}")
        lines.append(f"  Given: {sp.given_context or '– (MISSING)'}")
        lines.append(f"  When:  {sp.when_action or '– (MISSING)'}")
        lines.append(f"  Then:  {sp.then_expectation or '– (MISSING)'}")
        lines.append("")
    return "\n".join(lines)


def _tasks_context(tasks) -> str:
    if not tasks:
        return "No tasks recorded."
    lines = [f"TASKS TO REVIEW ({len(tasks)} total)\n"]
    for t in tasks:
        lines.append(f"[{t.id}]")
        lines.append(f"  Title: {t.title}")
        lines.append(f"  Complexity: {t.complexity}")
        lines.append(f"  Description: {t.description or '– (MISSING)'}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-category system prompts
# ---------------------------------------------------------------------------

_STORY_SYSTEM = """You are a QA Reviewer checking user stories for quality.

Your ONLY output is tool calls — no prose.

Rules:
1. If two stories describe the same need with different wording → call delete_story() on the weaker one.
2. If a story's wording is vague or incomplete → call update_user_story() to improve it.
3. If a story is clear and unique → do nothing (no tool call needed for it).

Use the exact UUIDs shown in the artifact list. Copy them precisely — do not invent IDs."""

_COMPONENT_SYSTEM = """You are a QA Reviewer checking architectural components for quality.

Your ONLY output is tool calls — no prose.

Rules:
1. If two components have the same responsibility with different names → call delete_component() on the redundant one.
2. If a component name is unclear or responsibility is vague → call update_component() to improve it.
3. If a component is well-defined and unique → do nothing.

Use the exact UUIDs shown in the artifact list."""

_DECISION_SYSTEM = """You are a QA Reviewer checking architecture decisions (ADRs) for quality.

Your ONLY output is tool calls — no prose.

Rules:
1. If two decisions address the same architectural concern → call delete_decision() on the weaker/less complete one.
2. If a decision title is unclear or the decision text is incomplete → call update_decision() to improve it.
3. If a decision is clear and unique → do nothing.

Use the exact UUIDs shown in the artifact list."""

_SPEC_SYSTEM = """You are a QA Reviewer checking test specifications for quality.

Your ONLY output is tool calls — no prose.

Rules:
1. If two specs test the same scenario → call delete_test_spec() on the duplicate.
2. If a spec has missing Given/When/Then fields (shown as '– (MISSING)') → call update_test_spec() to fill them in.
3. If a spec description is vague → call update_test_spec() to improve it.
4. If a spec is complete and unique → do nothing.

Use the exact UUIDs shown in the artifact list."""

_TASK_SYSTEM = """You are a QA Reviewer checking implementation tasks for quality.

Your ONLY output is tool calls — no prose.

Rules:
1. If two tasks implement the same thing → call delete_task() on the duplicate.
2. If a task has a missing or very short description (shown as '– (MISSING)') → call update_task() to add one.
3. If a task title is unclear → call update_task() to improve it.
4. If a task is well-defined and unique → do nothing.

Use the exact UUIDs shown in the artifact list."""

_HOLISTIC_SYSTEM = """You are a QA Reviewer doing a final consistency check across all artifact categories.

Your ONLY output is tool calls — no prose.

Check for CROSS-CATEGORY issues only (do not re-review single-category quality, that was already done):
1. Test specs with empty Given/When/Then that were missed → call update_test_spec()
2. Tasks with no description → call update_task()
3. Duplicate component names that slipped through (case differences, abbreviations) → call delete_component()
4. Duplicate decision titles that slipped through → call delete_decision()

If everything looks consistent, make no tool calls."""


# ---------------------------------------------------------------------------
# Single-pass executor
# ---------------------------------------------------------------------------

async def _run_pass(
    project_id: str,
    step_name: str,
    system_prompt: str,
    context_text: str,
    knowledge_svc: KnowledgeService,
) -> AsyncIterator[dict]:
    """Run one focused review pass and yield tool_used events."""
    if not context_text.strip():
        return

    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": context_text},
    ]

    log.info(f"[review/{step_name}] Starting pass — context={len(context_text)} chars")

    try:
        resp = await _client.chat.completions.create(
            model=settings.tdd_model,
            max_tokens=2048,
            messages=messages,
            tools=_REVIEW_TOOLS,
            tool_choice="auto",   # "required" causes unnecessary calls when nothing to fix
            stream=False,
        )
    except Exception as e:
        log.error(f"[review/{step_name}] LLM call failed: {e}")
        return

    message = resp.choices[0].message if resp.choices else None
    if not message or not message.tool_calls:
        log.info(f"[review/{step_name}] No changes needed (0 tool calls)")
        return

    log.info(f"[review/{step_name}] {len(message.tool_calls)} tool call(s)")
    for tc in message.tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            log.warning(f"[review/{step_name}] Bad JSON for {name}")
            continue

        result = await dispatch_tool(project_id, name, args, knowledge_svc)
        log.info(f"[review/{step_name}] {name} → {result}")
        yield {"type": "tool_used", "name": name, "result": result}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_full_review(
    project_id: str,
    db: AsyncSession,
) -> AsyncIterator[dict]:
    """
    Orchestrate the full multi-pass review. Yields a mix of:
      {"type": "review_progress", "step": "<name>", "status": "running"|"done", "label": "..."}
      {"type": "tool_used", "name": "...", "result": "..."}
    """
    svc = KnowledgeService(db)

    passes = [
        ("stories",    "Reviewing stories",             _STORY_SYSTEM,     lambda: svc.get_all_stories(project_id),    _stories_context),
        ("components", "Reviewing components",          _COMPONENT_SYSTEM, lambda: svc.get_all_components(project_id), _components_context),
        ("decisions",  "Reviewing decisions",           _DECISION_SYSTEM,  lambda: svc.get_all_decisions(project_id),  _decisions_context),
        ("specs",      "Reviewing test specs",          _SPEC_SYSTEM,      lambda: svc.get_all_test_specs(project_id), _specs_context),
        ("tasks",      "Reviewing tasks",               _TASK_SYSTEM,      lambda: svc.get_all_tasks(project_id),      _tasks_context),
    ]

    for step_key, label, system_prompt, fetcher, context_builder in passes:
        yield {"type": "review_progress", "step": step_key, "status": "running", "label": label}

        artifacts = await fetcher()
        context_text = context_builder(artifacts)

        async for event in _run_pass(project_id, step_key, system_prompt, context_text, svc):
            yield event

        yield {"type": "review_progress", "step": step_key, "status": "done", "label": label}

    # Final holistic pass — re-fetch everything after all per-category cleanups
    yield {"type": "review_progress", "step": "holistic", "status": "running", "label": "Final consistency check"}

    full_context = await svc.get_full_review_context(project_id)
    async for event in _run_pass(project_id, "holistic", _HOLISTIC_SYSTEM, full_context, svc):
        yield event

    yield {"type": "review_progress", "step": "holistic", "status": "done", "label": "Final consistency check"}
