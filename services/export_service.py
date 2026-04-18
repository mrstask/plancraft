"""Export service — builds task DAG JSON and arc42 Markdown from the knowledge model."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import (
    Project, Task, TaskDependency, TaskStory, TaskTestSpec,
    UserStory, Component, ArchitectureDecision, Constraint, TestSpec,
)
from services.knowledge import KnowledgeService


# ---------------------------------------------------------------------------
# Task DAG export
# ---------------------------------------------------------------------------

async def build_task_dag(project_id: str, db: AsyncSession) -> dict[str, Any]:
    svc = KnowledgeService(db)
    project = await svc._get_project(project_id)
    tasks = await svc.get_all_tasks(project_id)

    # Bulk-fetch all relationship rows for this project's tasks in 3 queries
    task_ids = [t.id for t in tasks]

    dep_rows: list[TaskDependency] = []
    story_rows: list[TaskStory] = []
    spec_rows: list[TaskTestSpec] = []

    if task_ids:
        dep_result = await db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
        )
        dep_rows = dep_result.scalars().all()

        story_result = await db.execute(
            select(TaskStory).where(TaskStory.task_id.in_(task_ids))
        )
        story_rows = story_result.scalars().all()

        spec_result = await db.execute(
            select(TaskTestSpec).where(TaskTestSpec.task_id.in_(task_ids))
        )
        spec_rows = spec_result.scalars().all()

    # Index by task_id
    deps_by_task: dict[str, list[str]] = defaultdict(list)
    for row in dep_rows:
        deps_by_task[row.task_id].append(row.depends_on_id)

    stories_by_task: dict[str, list[str]] = defaultdict(list)
    for row in story_rows:
        stories_by_task[row.task_id].append(row.story_id)

    specs_by_task: dict[str, list[str]] = defaultdict(list)
    for row in spec_rows:
        specs_by_task[row.task_id].append(row.spec_id)

    # Complexity summary
    by_complexity: dict[str, int] = {"trivial": 0, "small": 0, "medium": 0, "large": 0}
    task_list = []
    for task in tasks:
        complexity = task.complexity or "medium"
        if complexity in by_complexity:
            by_complexity[complexity] += 1
        else:
            by_complexity[complexity] = by_complexity.get(complexity, 0) + 1

        task_list.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "complexity": complexity,
            "status": "backlog",
            "acceptance_criteria": task.acceptance_criteria or [],
            "file_paths": task.file_paths or [],
            "depends_on": deps_by_task.get(task.id, []),
            "story_ids": stories_by_task.get(task.id, []),
            "test_spec_ids": specs_by_task.get(task.id, []),
        })

    return {
        "project": project.name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tasks": task_list,
        "summary": {
            "total": len(task_list),
            "by_complexity": by_complexity,
        },
    }


# ---------------------------------------------------------------------------
# arc42 Markdown export
# ---------------------------------------------------------------------------

_PLACEHOLDER = "> *Not yet captured.*"

_EXTERNAL_TYPES = {"gateway", "api", "cli", "external"}


def _placeholder_if_empty(lines: list[str]) -> str:
    return "\n".join(lines) if lines else _PLACEHOLDER


async def build_arc42(project_id: str, db: AsyncSession) -> str:
    svc = KnowledgeService(db)
    project = await svc._get_project(project_id)

    constraints = await svc.get_all_constraints(project_id)
    components = await svc.get_all_components(project_id)
    decisions = await svc.get_all_decisions(project_id)
    stories = await svc.get_all_stories(project_id)
    specs = await svc.get_all_test_specs(project_id)
    tasks = await svc.get_all_tasks(project_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections: list[str] = []

    # Header
    sections.append(f"# arc42 Architecture Documentation\n# {project.name}")
    sections.append(f"*Generated: {now}*\n\n---")

    # 1. Introduction and Goals
    purpose = project.description or _PLACEHOLDER
    # Quality goals: derive from must-have stories
    must_stories = [s for s in stories if (s.priority or "should") == "must"]
    qg_lines = [
        f"- {s.i_want} *(as a {s.as_a})*"
        for s in (must_stories or stories[:3])
    ]
    quality_block = _placeholder_if_empty(qg_lines)

    sections.append(
        "## 1. Introduction and Goals\n\n"
        f"### Purpose\n{purpose}\n\n"
        f"### Quality Goals\n{quality_block}\n\n"
        f"### Stakeholders\n{_PLACEHOLDER}"
    )
    sections.append("---")

    # 2. Constraints
    constraint_lines = [f"- **{c.type}**: {c.description}" for c in constraints]
    sections.append(f"## 2. Constraints\n\n{_placeholder_if_empty(constraint_lines)}")
    sections.append("---")

    # 3. System Context
    external = [
        c for c in components
        if (c.component_type or "").lower() in _EXTERNAL_TYPES
    ]
    ext_block = (
        "\n".join(f"- **{c.name}** ({c.component_type}): {c.responsibility}" for c in external)
        if external else _PLACEHOLDER
    )
    sections.append(
        "## 3. System Context\n\n"
        "> *Diagram not yet generated. Components and their relationships are defined in section 5.*\n\n"
        f"### External Interfaces\n{ext_block}"
    )
    sections.append("---")

    # 4. Solution Strategy
    strategy_lines = [f"- **{d.title}**: {d.decision}" for d in decisions]
    sections.append(f"## 4. Solution Strategy\n\n{_placeholder_if_empty(strategy_lines)}")
    sections.append("---")

    # 5. Building Blocks
    component_blocks: list[str] = []
    for comp in components:
        block_lines = [
            f"### {comp.name}",
            f"**Type:** {comp.component_type or '–'}",
            f"**Responsibility:** {comp.responsibility}",
        ]
        if comp.file_paths:
            paths = ", ".join(f"`{p}`" for p in comp.file_paths)
            block_lines.append(f"**Files:** {paths}")
        component_blocks.append("\n".join(block_lines))

    building_block_body = (
        "\n\n".join(component_blocks) if component_blocks else _PLACEHOLDER
    )
    sections.append(f"## 5. Building Blocks\n\n{building_block_body}")
    sections.append("---")

    # 6. Runtime View — task list with spec counts
    task_lines: list[str] = []
    for i, t in enumerate(tasks):
        task_lines.append(f"{i + 1}. **{t.title}** *(complexity: {t.complexity or 'medium'})*")
        if t.acceptance_criteria:
            for ac in t.acceptance_criteria:
                task_lines.append(f"   - {ac}")
    task_block = "\n".join(task_lines) if task_lines else _PLACEHOLDER

    spec_by_type: dict[str, list] = {"unit": [], "integration": [], "e2e": []}
    for sp in specs:
        spec_by_type.setdefault(sp.test_type or "unit", []).append(sp)
    spec_summary_lines = [
        f"- **Unit tests:** {len(spec_by_type['unit'])}",
        f"- **Integration tests:** {len(spec_by_type['integration'])}",
        f"- **End-to-end tests:** {len(spec_by_type['e2e'])}",
        f"- **Total:** {len(specs)}",
    ]

    sections.append(
        "## 6. Runtime View\n\n"
        "> *Sequence diagrams not yet generated.*\n\n"
        f"### Implementation Tasks ({len(tasks)})\n{task_block}\n\n"
        f"### Test Coverage Summary\n" + "\n".join(spec_summary_lines)
    )
    sections.append("---")

    # 7. Deployment View
    sections.append(
        "## 7. Deployment View\n\n"
        "> *Deployment diagram not yet generated.*"
    )
    sections.append("---")

    # 8. Cross-cutting Concepts — test specifications catalogue
    spec_blocks: list[str] = []
    for sp in specs:
        sb = [f"#### {sp.description}"]
        sb.append(f"**Type:** {sp.test_type or 'unit'}")
        if sp.given_context:
            sb.append(f"**Given:** {sp.given_context}")
        if sp.when_action:
            sb.append(f"**When:** {sp.when_action}")
        if sp.then_expectation:
            sb.append(f"**Then:** {sp.then_expectation}")
        spec_blocks.append("\n".join(sb))

    spec_catalogue = (
        "### Test Specifications\n\n" + "\n\n".join(spec_blocks)
        if spec_blocks else _PLACEHOLDER
    )
    sections.append(f"## 8. Cross-cutting Concepts\n\n{spec_catalogue}")
    sections.append("---")

    # 9. Architecture Decisions
    adr_blocks: list[str] = []
    for n, dec in enumerate(decisions, start=1):
        adr = [f"### ADR-{n}: {dec.title}", ""]
        adr.append(f"**Context:** {dec.context or '–'}")
        adr.append("")
        adr.append(f"**Decision:** {dec.decision}")
        adr.append("")
        consequences = dec.consequences or {}
        positives = consequences.get("positive") or []
        negatives = consequences.get("negative") or []
        if positives:
            adr.append("**Positive:**")
            adr.extend(f"- {p}" for p in positives)
            adr.append("")
        if negatives:
            adr.append("**Trade-offs:**")
            adr.extend(f"- {n_item}" for n_item in negatives)
            adr.append("")
        adr_blocks.append("\n".join(adr))

    adr_body = "\n\n".join(adr_blocks) if adr_blocks else _PLACEHOLDER
    sections.append(f"## 9. Architecture Decisions\n\n{adr_body}")
    sections.append("---")

    # 10. Quality Requirements — stories grouped by priority
    priority_order = ["must", "should", "could", "wont"]
    by_priority: dict[str, list[UserStory]] = defaultdict(list)
    for story in stories:
        by_priority[story.priority or "should"].append(story)

    story_sections: list[str] = []
    for prio in priority_order:
        prio_stories = by_priority.get(prio, [])
        if not prio_stories:
            continue
        story_sections.append(f"### {prio.capitalize()}")
        for s in prio_stories:
            story_sections.append(
                f"- As a **{s.as_a}**, I want {s.i_want}, so that {s.so_that}"
            )

    quality_req_body = "\n".join(story_sections) if story_sections else _PLACEHOLDER
    spec_count_line = (
        f"\n### Test Coverage\n{len(specs)} test spec{'s' if len(specs) != 1 else ''} defined"
        f" ({len(spec_by_type['unit'])} unit, {len(spec_by_type['integration'])} integration,"
        f" {len(spec_by_type['e2e'])} e2e)."
        if specs else ""
    )
    sections.append(
        f"## 10. Quality Requirements\n\n### Stories by Priority\n\n{quality_req_body}"
        f"{spec_count_line}"
    )
    sections.append("---")

    # 11. Risks and Technical Debt
    sections.append(f"## 11. Risks and Technical Debt\n\n{_PLACEHOLDER}")
    sections.append("---")

    # 12. Glossary
    sections.append(f"## 12. Glossary\n\n{_PLACEHOLDER}")

    return "\n\n".join(sections) + "\n"
