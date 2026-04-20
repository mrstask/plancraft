"""Per-role context file renderer.

Writes .plancraft/role-context/{role}.md files with strictly scoped content
so each role only loads the artifacts it needs — keeping local-model context small.

Token budget targets per role (approximate, at ~4 chars/token):
  ba        ~800  tokens  — problem + constraints only
  pm        ~2000 tokens  — stories + epics + MVP scope (needs full IDs)
  architect ~1500 tokens  — components + decisions
  tdd       ~3000 tokens  — stories + components + specs + tasks (needs full IDs)
  review    ~4000 tokens  — everything (reviewer must see all artifacts)
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from services.export.queries import ExportDataLoader
from services.knowledge.queries import ArtifactQueries
from services.workspace.workspace import ProjectWorkspace

log = logging.getLogger(__name__)

# Soft character budget per role file (not a hard truncation — just a guideline logged)
_BUDGET: dict[str, int] = {
    "ba": 3_200,
    "pm": 8_000,
    "architect": 6_000,
    "tdd": 12_000,
    "review": 16_000,
}


async def render_ba(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    constraints = await queries.get_all_constraints(project_id)

    lines = [
        f"# BA Context: {project.name}",
        "",
        "## Problem Statement",
        "",
        project.description or "> *Not yet defined.*",
        "",
    ]
    if constraints:
        lines += [f"## Constraints ({len(constraints)})", ""]
        for c in constraints:
            lines.append(f"- **{c.type}**: {c.description}")
    else:
        lines += ["## Constraints", "", "> *None recorded yet.*"]

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("ba")
    path.write_text(content, encoding="utf-8")
    _log_budget("ba", content)
    return path


async def render_pm(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    stories = await queries.get_all_stories(project_id)
    epics = await queries.get_all_epics(project_id)

    lines = [
        f"# PM Context: {project.name}",
        "",
        f"Problem: {project.description or '(none)'}",
        "",
        f"## STORIES ({len(stories)}) — use these FULL IDs in update_user_story() and set_mvp_scope()",
        "",
    ]
    for story in stories:
        lines.append(f"[{story.id}] As a {story.as_a}, I want {story.i_want}, so that {story.so_that}")
        lines.append(f"  Priority: {story.priority}")
        if story.epic_id:
            lines.append(f"  Epic ID: {story.epic_id}")
        for ac in (story.acceptance_criteria or []):
            lines.append(f"  AC: {ac.criterion}")

    if epics:
        lines += ["", f"## EPICS ({len(epics)})", ""]
        for epic in epics:
            lines.append(f"[{epic.id}] {epic.title}: {epic.description or '(no description)'}")
    else:
        lines += ["", "## EPICS — none recorded yet"]

    if project.mvp_story_ids:
        lines += ["", "## CURRENT MVP SCOPE", ""]
        for sid in project.mvp_story_ids:
            lines.append(f"- {sid}")
        if project.mvp_rationale:
            lines.append(f"\nRationale: {project.mvp_rationale}")

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("pm")
    path.write_text(content, encoding="utf-8")
    _log_budget("pm", content)
    return path


async def render_architect(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    components = await queries.get_all_components(project_id)
    decisions = await queries.get_all_decisions(project_id)

    lines = [
        f"# Architect Context: {project.name}",
        "",
        f"Problem: {project.description or '(none)'}",
        "",
        f"## COMPONENTS ({len(components)}) — use these FULL IDs in component_id field",
        "",
    ]
    for c in components:
        lines.append(f"[{c.id}] {c.name} ({c.component_type or 'module'}): {c.responsibility}")
        if c.file_paths:
            lines.append(f"  Files: {', '.join(c.file_paths)}")

    if decisions:
        lines += ["", f"## ARCHITECTURE DECISIONS ({len(decisions)})", ""]
        for d in decisions:
            lines.append(f"[{d.id}] {d.title}")
            lines.append(f"  Decision: {d.decision}")
            if d.context:
                lines.append(f"  Context: {d.context}")
    else:
        lines += ["", "## ARCHITECTURE DECISIONS — none recorded yet"]

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("architect")
    path.write_text(content, encoding="utf-8")
    _log_budget("architect", content)
    return path


async def render_tdd(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    stories = await queries.get_all_stories(project_id)
    components = await queries.get_all_components(project_id)
    specs = await queries.get_all_test_specs(project_id)
    tasks = await queries.get_all_tasks(project_id)

    lines = [
        f"# TDD Context: {project.name}",
        "",
        f"Problem: {project.description or '(none)'}",
        "",
    ]
    if project.mvp_story_ids:
        lines.append(f"MVP scope: {len(project.mvp_story_ids)} stor{'y' if len(project.mvp_story_ids) == 1 else 'ies'} selected")
        if project.mvp_rationale:
            lines.append(f"MVP rationale: {project.mvp_rationale}")
        lines.append("")

    lines += [f"## USER STORIES ({len(stories)}) — use these FULL IDs in story_id / story_ids fields", ""]
    for s in stories:
        lines.append(f"[{s.id}] As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
        lines.append(f"  Priority: {s.priority}")
        for ac in (s.acceptance_criteria or []):
            lines.append(f"  AC: {ac.criterion}")

    lines += ["", f"## COMPONENTS ({len(components)}) — use these FULL IDs in component_id field", ""]
    for c in components:
        lines.append(f"[{c.id}] {c.name} ({c.component_type or 'module'}): {c.responsibility}")

    if specs:
        lines += ["", f"## TEST SPECS ALREADY SAVED ({len(specs)}) — do NOT duplicate these", ""]
        for sp in specs:
            lines.append(f"[{sp.id}] {sp.description} [{sp.test_type}]")
    else:
        lines += ["", "## TEST SPECS — none saved yet; you must create all of them now"]

    if tasks:
        lines += ["", f"## TASKS ALREADY PROPOSED ({len(tasks)}) — do NOT duplicate these", ""]
        for t in tasks:
            lines.append(f"[{t.id}] {t.title} [{t.complexity}]")
    else:
        lines += ["", "## TASKS — none proposed yet; you must propose all implementation tasks now"]

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("tdd")
    path.write_text(content, encoding="utf-8")
    _log_budget("tdd", content)
    return path


async def render_review(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    stories = await queries.get_all_stories(project_id)
    components = await queries.get_all_components(project_id)
    decisions = await queries.get_all_decisions(project_id)
    specs = await queries.get_all_test_specs(project_id)
    tasks = await queries.get_all_tasks(project_id)

    lines = [
        f"# Review Context: {project.name}",
        "",
        f"Problem: {project.description or '(none)'}",
        "",
        "=" * 60,
        "ALL ARTIFACTS — review every category for duplicates and quality",
        "=" * 60,
        "",
        f"### STORIES ({len(stories)})",
        "",
    ]
    for s in stories:
        lines.append(f"[{s.id}]")
        lines.append(f"  As a {s.as_a}, I want {s.i_want}, so that {s.so_that}")
        lines.append(f"  Priority: {s.priority}")
        for ac in (s.acceptance_criteria or []):
            lines.append(f"  AC: {ac.criterion}")

    lines += ["", f"### COMPONENTS ({len(components)})", ""]
    for c in components:
        lines.append(f"[{c.id}] {c.name} ({c.component_type or '–'}): {c.responsibility}")

    lines += ["", f"### ARCHITECTURE DECISIONS ({len(decisions)})", ""]
    for d in decisions:
        lines.append(f"[{d.id}] {d.title}")
        lines.append(f"  Decision: {d.decision}")
        if d.context:
            lines.append(f"  Context: {d.context}")

    lines += ["", f"### TEST SPECS ({len(specs)})", ""]
    for sp in specs:
        lines.append(f"[{sp.id}] {sp.description} [{sp.test_type}]")
        if sp.given_context:
            lines.append(f"  Given: {sp.given_context}")
        if sp.when_action:
            lines.append(f"  When: {sp.when_action}")
        if sp.then_expectation:
            lines.append(f"  Then: {sp.then_expectation}")

    lines += ["", f"### TASKS ({len(tasks)})", ""]
    for t in tasks:
        lines.append(f"[{t.id}] {t.title} [{t.complexity}]")
        lines.append(f"  Description: {t.description}")

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("review")
    path.write_text(content, encoding="utf-8")
    _log_budget("review", content)
    return path


async def render_all_roles(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> list[Path]:
    return [
        await render_ba(ws, project_id, db),
        await render_pm(ws, project_id, db),
        await render_architect(ws, project_id, db),
        await render_tdd(ws, project_id, db),
        await render_review(ws, project_id, db),
    ]


def _log_budget(role: str, content: str) -> None:
    budget = _BUDGET.get(role, 0)
    size = len(content)
    if size > budget:
        log.warning("Role context '%s' is %d chars (budget %d) — consider trimming", role, size, budget)
