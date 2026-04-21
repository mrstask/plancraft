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

from roles.ba_clarifications import CATALOG_BY_ID, REQUIRED_IDS
from services.export.queries import ExportDataLoader
from services.knowledge.queries import ArtifactQueries
from services.workspace.workspace import ProjectWorkspace

log = logging.getLogger(__name__)

# Soft character budget per role file (not a hard truncation — just a guideline logged)
_BUDGET: dict[str, int] = {
    "founder": 6_000,
    "ba": 6_400,  # expanded to cover new BA artifact sections
    "pm": 8_000,
    "architect": 6_000,
    "tdd": 12_000,
    "review": 16_000,
}


async def _founder_lines(queries: ArtifactQueries, project_id: str) -> list[str]:
    mission = await queries.get_project_mission(project_id)
    roadmap_items = await queries.get_all_roadmap_items(project_id)
    tech_entries = await queries.get_all_tech_stack_entries(project_id)

    lines = ["## FOUNDER ARTIFACTS", ""]

    lines += ["### Mission", ""]
    if mission and any([mission.statement, mission.target_users, mission.problem]):
        lines.append(mission.statement or "> *Mission statement not yet defined.*")
        lines.append("")
        lines.append(f"Target users: {mission.target_users or '(not set)'}")
        lines.append(f"Problem: {mission.problem or '(not set)'}")
    else:
        lines.append("> *Mission not yet captured — call set_project_mission().*")
    lines.append("")

    lines += [f"### Roadmap ({len(roadmap_items)})", ""]
    if roadmap_items:
        for item in roadmap_items:
            prefix = "[MVP] " if item.mvp else ""
            epic_ref = f" -> epic {item.linked_epic_id}" if item.linked_epic_id else ""
            lines.append(f"{item.ordinal}. {prefix}{item.title}{epic_ref}")
            lines.append(f"   {item.description}")
    else:
        lines.append("> *No roadmap items yet — call add_roadmap_item().*")
    lines.append("")

    lines += [f"### Tech Stack ({len(tech_entries)})", ""]
    if tech_entries:
        for entry in tech_entries:
            lines.append(f"- {entry.layer}: {entry.choice}")
            lines.append(f"  Why: {entry.rationale}")
    else:
        lines.append("> *No tech stack entries yet — call add_tech_stack_entry().*")
    lines.append("")

    return lines


async def render_founder(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    lines = [
        f"# Founder Context: {project.name}",
        "",
        "## Initial Project Description",
        "",
        project.description or "> *Not yet defined.*",
        "",
    ]
    lines += await _founder_lines(queries, project_id)

    content = "\n".join(lines) + "\n"
    path = ws.role_context_file("founder")
    path.write_text(content, encoding="utf-8")
    _log_budget("founder", content)
    return path


async def render_ba(ws: ProjectWorkspace, project_id: str, db: AsyncSession) -> Path:
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    constraints = await queries.get_all_constraints(project_id)
    personas = await queries.get_all_personas(project_id)
    flows = await queries.get_all_user_flows(project_id)
    business_rules = await queries.get_all_business_rules(project_id)
    entities = await queries.get_all_data_entities(project_id)
    frs = await queries.get_all_functional_requirements(project_id)
    pending_ids = await queries.get_pending_clarification_ids(project_id)

    lines = [
        f"# BA Context: {project.name}",
        "",
        "## Problem Statement",
        "",
        project.description or "> *Not yet defined.*",
        "",
    ]
    lines += await _founder_lines(queries, project_id)

    # Vision & Scope
    lines += ["## Vision & Scope", ""]
    if project.business_goals:
        lines.append("**Business goals:**")
        for g in project.business_goals:
            lines.append(f"- {g}")
    if project.success_metrics:
        lines.append("**Success metrics:**")
        for m in project.success_metrics:
            lines.append(f"- {m}")
    if project.in_scope:
        lines.append("**In scope:**")
        for item in project.in_scope:
            lines.append(f"- {item}")
    if project.out_of_scope:
        lines.append("**Out of scope:**")
        for item in project.out_of_scope:
            lines.append(f"- {item}")
    if project.target_users:
        lines.append(f"**Target users:** {', '.join(project.target_users)}")
    if not any([project.business_goals, project.success_metrics, project.in_scope]):
        lines.append("> *Not yet populated — call set_vision_scope().*")
    lines.append("")

    # Clarification status
    lines += [f"## Clarification Points — {len(pending_ids)} pending", ""]
    if pending_ids:
        lines.append("**Still pending (required):**")
        for pid in pending_ids:
            point = CATALOG_BY_ID.get(pid)
            label = point.name if point else pid
            lines.append(f"- `{pid}`: {label}")
    else:
        lines.append("> All required clarification points answered.")
    lines.append("")

    # Personas
    if personas:
        lines += [f"## Personas ({len(personas)})", ""]
        for p in personas:
            lines.append(f"**{p.name}** — {p.role}")
            if p.goals:
                lines.append(f"  Goals: {'; '.join(p.goals)}")
            if p.pain_points:
                lines.append(f"  Pain points: {'; '.join(p.pain_points)}")
    else:
        lines += ["## Personas", "", "> *None recorded yet — call add_persona().*"]
    lines.append("")

    # User Flows
    if flows:
        lines += [f"## User Flows ({len(flows)})", ""]
        for flow in flows:
            lines.append(f"**{flow.name}**")
            if flow.description:
                lines.append(f"  {flow.description}")
            for step in sorted(flow.steps, key=lambda s: s.order_index):
                actor_prefix = f"{step.actor}: " if step.actor else ""
                lines.append(f"  {step.order_index + 1}. {actor_prefix}{step.description}")
    else:
        lines += ["## User Flows", "", "> *None recorded yet — call add_user_flow().*"]
    lines.append("")

    # Business Rules
    if business_rules:
        lines += [f"## Business Rules ({len(business_rules)})", ""]
        for rule in business_rules:
            applies = f" (applies to: {', '.join(rule.applies_to)})" if rule.applies_to else ""
            lines.append(f"- {rule.rule}{applies}")
    else:
        lines += ["## Business Rules", "", "> *None recorded yet — call add_business_rule().*"]
    lines.append("")

    # Data Entities
    if entities:
        lines += [f"## Data Entities ({len(entities)})", ""]
        for e in entities:
            lines.append(f"**{e.name}**")
            if e.attributes:
                lines.append(f"  Attributes: {'; '.join(e.attributes)}")
            if e.relationships:
                lines.append(f"  Relationships: {'; '.join(e.relationships)}")
    else:
        lines += ["## Data Entities", "", "> *None recorded yet — call add_data_entity().*"]
    lines.append("")

    # Functional Requirements
    if frs:
        lines += [f"## Functional Requirements ({len(frs)})", ""]
        for fr in frs:
            lines.append(f"- {fr.description}")
            if fr.inputs:
                lines.append(f"  Inputs: {', '.join(fr.inputs)}")
            if fr.outputs:
                lines.append(f"  Outputs: {', '.join(fr.outputs)}")
    else:
        lines += ["## Functional Requirements", "", "> *None recorded yet — call add_functional_requirement().*"]
    lines.append("")

    # Constraints
    if constraints:
        lines += [f"## Constraints ({len(constraints)})", ""]
        for c in constraints:
            lines.append(f"- **{c.type}**: {c.description}")
    else:
        lines += ["## Constraints", "", "> *None recorded yet.*"]
    lines.append("")

    # Glossary
    if project.terminology:
        lines += [f"## Glossary ({len(project.terminology)} terms)", ""]
        for entry in project.terminology:
            lines.append(f"- **{entry['term']}**: {entry['definition']}")
    else:
        lines += ["## Glossary", "", "> *No domain terms defined yet.*"]

    # LLM Interaction Model
    if project.llm_interaction_model:
        m = project.llm_interaction_model
        lines += ["", "## LLM Interaction Model", ""]
        lines.append(f"- Role: {m.get('llm_role', '–')}")
        lines.append(f"- Pattern: {m.get('interaction_pattern', '–')}")
        lines.append(f"- Memory: {m.get('memory_strategy', '–')}")
        if m.get("error_handling"):
            lines.append(f"- Error handling: {'; '.join(m['error_handling'])}")

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
    ]
    lines += await _founder_lines(queries, project_id)
    lines += [
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
    contracts = await queries.get_all_interface_contracts(project_id)

    lines = [
        f"# Architect Context: {project.name}",
        "",
        f"Problem: {project.description or '(none)'}",
        "",
    ]
    lines += await _founder_lines(queries, project_id)
    lines += [
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

    if contracts:
        lines += ["", f"## INTERFACE CONTRACTS ({len(contracts)})", ""]
        for contract in contracts:
            component_name = contract.component.name if contract.component else contract.component_id
            lines.append(f"[{contract.id}] {contract.name} ({contract.kind}) on {component_name}")
    else:
        lines += ["", "## INTERFACE CONTRACTS — none recorded yet"]

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
    lines += await _founder_lines(queries, project_id)
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
    ]
    lines += await _founder_lines(queries, project_id)

    # Constitution — reviewer must apply its rules
    if project.constitution_md:
        lines += ["## CONSTITUTION", "", project.constitution_md.strip(), ""]

    lines += [
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
        await render_founder(ws, project_id, db),
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
