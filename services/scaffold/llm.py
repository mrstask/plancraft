"""LLM orchestration layer for the Scaffolder phase.

Follows the same non-streaming pattern as services/review_orchestrator.py.
The LLM is called with tool_choice="required" so it must emit tool calls.
Tool calls are dispatched locally (file writes), NOT through KnowledgeService.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.db import Component, InterfaceContract, Task, TestSpec
from roles.scaffolder import ScaffolderRole

if TYPE_CHECKING:
    from services.scaffold.tech_stack_reader import ScaffoldConfig

log = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _snake(name: str) -> str:
    return _SLUG_RE.sub("_", name.lower()).strip("_")


def _pascal(name: str) -> str:
    return "".join(p.capitalize() for p in _SLUG_RE.split(name.lower()) if p)


# Tool schemas

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_backend_module",
            "description": (
                "Write a Python stub module under backend/src/<package>/. "
                "Every method body must be raise NotImplementedError('TODO: TASK-NNN'). "
                "First line of content must be: # generated-by: plancraft-scaffolder"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module_name": {"type": "string", "description": "snake_case filename without .py"},
                    "component_id": {"type": "string", "description": "Component ID from context"},
                    "content": {"type": "string", "description": "Full Python source code"},
                },
                "required": ["module_name", "component_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_frontend_module",
            "description": (
                "Write a TypeScript/React stub under frontend/src/. "
                "Every exported function body must be throw new Error('TODO: TASK-NNN'). "
                "First line must be: // generated-by: plancraft-scaffolder"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module_name": {"type": "string", "description": "PascalCase filename without extension"},
                    "component_id": {"type": "string", "description": "Component ID from context"},
                    "content": {"type": "string", "description": "Full TypeScript source code"},
                },
                "required": ["module_name", "component_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_backend_test",
            "description": (
                "Write a pytest stub test file under backend/tests/. "
                "Must import the stub and call it — tests MUST fail by construction. "
                "First line must be: # generated-by: plancraft-scaffolder"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "test_file_name": {"type": "string", "description": "test_snake_case without .py"},
                    "spec_id": {"type": "string", "description": "TestSpec ID from context"},
                    "content": {"type": "string", "description": "Full pytest source code"},
                },
                "required": ["test_file_name", "spec_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_frontend_test",
            "description": (
                "Write a vitest stub test under frontend/tests/. "
                "Must import from the stub module. "
                "First line must be: // generated-by: plancraft-scaffolder"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "test_file_name": {"type": "string", "description": "PascalCase filename without extension"},
                    "spec_id": {"type": "string", "description": "TestSpec ID from context"},
                    "content": {"type": "string", "description": "Full vitest/TypeScript source code"},
                },
                "required": ["test_file_name", "spec_id", "content"],
            },
        },
    },
]


# Context builder

async def _build_context(
    project_id: str,
    db: AsyncSession,
    config: "ScaffoldConfig",
) -> str:
    components = (await db.execute(
        select(Component).where(Component.project_id == project_id).order_by(Component.created_at)
    )).scalars().all()

    contracts = (await db.execute(
        select(InterfaceContract)
        .where(InterfaceContract.project_id == project_id)
        .order_by(InterfaceContract.updated_at)
    )).scalars().all()

    tasks = (await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
    )).scalars().all()

    specs = (await db.execute(
        select(TestSpec).where(TestSpec.project_id == project_id).order_by(TestSpec.created_at)
    )).scalars().all()

    lines = [
        f"package_slug: {config.package_slug}",
        f"has_frontend: {config.has_frontend}",
        "",
        f"COMPONENTS ({len(components)}):",
    ]
    for c in components:
        lines += [
            f"  [{c.id}] {c.name} ({c.component_type or 'service'})",
            f"    responsibility: {c.responsibility}",
            f"    python_module: {_snake(c.name)}",
        ]
        if config.has_frontend:
            lines.append(f"    ts_module: {_pascal(c.name)}")

    if contracts:
        lines += ["", f"INTERFACE CONTRACTS ({len(contracts)}):"]
        for ct in contracts:
            lines += [
                f"  [{ct.id}] {ct.name} (kind={ct.kind}, component={ct.component_id})",
            ]
            if ct.body_md:
                lines.append(f"    summary: {ct.body_md[:300]}")

    if tasks:
        lines += ["", f"TASKS ({len(tasks)}):"]
        for t in tasks:
            lines.append(f"  [{t.id}] {t.title}")

    if specs:
        lines += ["", f"TEST SPECS ({len(specs)}):"]
        for s in specs:
            lines += [
                f"  [{s.id}] {s.description} ({s.test_type})",
                f"    component_id: {s.component_id or 'none'}",
            ]
            if s.given_context:
                lines.append(f"    given: {s.given_context}")
            if s.when_action:
                lines.append(f"    when: {s.when_action}")
            if s.then_expectation:
                lines.append(f"    then: {s.then_expectation}")

    return "\n".join(lines)


# Tool dispatch

def _dispatch(
    tool_name: str,
    args: dict,
    impl_dir: Path,
    config: "ScaffoldConfig",
) -> tuple[str, Path | None]:
    """Write a source file. Returns (message, path_or_None)."""
    try:
        pkg = config.package_slug
        if tool_name == "create_backend_module":
            name = args["module_name"]
            path = impl_dir / "backend" / "src" / pkg / f"{name}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return f"Written backend/src/{pkg}/{name}.py", path

        elif tool_name == "create_frontend_module":
            name = args["module_name"]
            path = impl_dir / "frontend" / "src" / f"{name}.tsx"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return f"Written frontend/src/{name}.tsx", path

        elif tool_name == "create_backend_test":
            name = args["test_file_name"]
            path = impl_dir / "backend" / "tests" / f"{name}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return f"Written backend/tests/{name}.py", path

        elif tool_name == "create_frontend_test":
            name = args["test_file_name"]
            path = impl_dir / "frontend" / "tests" / f"{name}.test.tsx"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return f"Written frontend/tests/{name}.test.tsx", path

        return f"Unknown scaffolder tool: {tool_name}", None
    except Exception as exc:
        log.error("Scaffolder tool %s failed: %s", tool_name, exc, exc_info=True)
        return f"Error in {tool_name}: {exc}", None


# Public entry point

async def run_scaffolder_llm(
    project_id: str,
    db: AsyncSession,
    impl_dir: Path,
    config: "ScaffoldConfig",
) -> AsyncIterator[dict]:
    """Call the LLM Scaffolder and dispatch tool calls to write source files.

    Yields:
        {"type": "scaffold_progress", "message": "..."}
        {"type": "file_written", "tool": "...", "path": "...", "message": "..."}
    """
    role = ScaffolderRole()
    context = await _build_context(project_id, db, config)

    system_prompt = (
        f"You are {role.name} for this project.\n\n"
        f"{role.system_prompt_fragment}\n\n"
        f"## Project Knowledge\n{context}"
    )
    user_msg = (
        "Generate the complete implementation skeleton now. "
        "Call create_backend_module() for every component, "
        "create_backend_test() for every test spec"
        + (
            ", create_frontend_module() and create_frontend_test() for frontend components"
            if config.has_frontend else ""
        )
        + ". Do not skip any component or spec."
    )

    log.info("[scaffolder] Starting LLM pass for project %s", project_id)
    yield {"type": "scaffold_progress", "message": "LLM scaffolding started"}

    try:
        resp = await _client.chat.completions.create(
            model=settings.ollama_model,
            max_tokens=settings.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=_TOOLS,
            tool_choice="required",
            stream=False,
        )
    except Exception as exc:
        log.error("[scaffolder] LLM call failed: %s", exc)
        yield {"type": "scaffold_progress", "message": f"LLM call failed: {exc}"}
        return

    message = resp.choices[0].message if resp.choices else None
    if not message or not message.tool_calls:
        log.warning("[scaffolder] LLM returned no tool calls")
        yield {"type": "scaffold_progress", "message": "LLM returned no tool calls — empty scaffold"}
        return

    log.info("[scaffolder] Dispatching %d tool call(s)", len(message.tool_calls))

    for tc in message.tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            log.warning("[scaffolder] Bad JSON for tool %s", name)
            continue

        msg, path = _dispatch(name, args, impl_dir, config)
        log.info("[scaffolder] %s -> %s", name, msg)

        if path:
            yield {
                "type": "file_written",
                "tool": name,
                "path": str(path.relative_to(impl_dir.parent)),
                "message": msg,
            }
        else:
            yield {"type": "scaffold_progress", "message": msg}

    yield {"type": "scaffold_progress", "message": "LLM scaffolding complete"}
