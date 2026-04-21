"""Export service — pluggable orchestrator + legacy build functions."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models.db import UserStory
from services.export.queries import BAExportData, ExportDataLoader


# ---------------------------------------------------------------------------
# Pluggable orchestrator (M6)
# ---------------------------------------------------------------------------

async def build_export(
    target_name: str,
    project_id: str,
    out_dir: Path,
    db: AsyncSession,
):
    """Build an export using the named target and run its validator.

    Returns the populated BuildResult with schema_valid / schema_errors set.
    """
    from services.export.targets import get_target
    from services.export.validators import run_validator

    target = get_target(target_name)
    result = await target.build(project_id, out_dir, db)
    return run_validator(target_name, result)


# ---------------------------------------------------------------------------
# Task DAG export
# ---------------------------------------------------------------------------

async def build_task_dag(project_id: str, db: AsyncSession) -> dict[str, Any]:
    loader = ExportDataLoader(db)
    data = await loader.load_task_export(project_id)

    # Complexity summary
    by_complexity: dict[str, int] = {"trivial": 0, "small": 0, "medium": 0, "large": 0}
    task_list = []
    for task in data.tasks:
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
            "depends_on": data.deps_by_task.get(task.id, []),
            "story_ids": data.stories_by_task.get(task.id, []),
            "test_spec_ids": data.specs_by_task.get(task.id, []),
        })

    return {
        "project": data.project_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tasks": task_list,
        "summary": {
            "total": len(task_list),
            "by_complexity": by_complexity,
        },
    }


# ---------------------------------------------------------------------------
# BA bundle JSON export (all 8 BA artifacts in one payload)
# ---------------------------------------------------------------------------

async def build_ba_bundle(project_id: str, db: AsyncSession) -> dict[str, Any]:
    loader = ExportDataLoader(db)
    data: BAExportData = await loader.load_ba_export(project_id)
    now = datetime.now(timezone.utc).isoformat()

    vision_scope = {
        "problem_statement": data.problem_statement or "",
        "target_users": data.target_users,
        "business_goals": data.business_goals,
        "success_metrics": data.success_metrics,
        "in_scope": data.in_scope,
        "out_of_scope": data.out_of_scope,
    }

    personas = [
        {
            "name": p.name,
            "role": p.role,
            "goals": list(p.goals or []),
            "pain_points": list(p.pain_points or []),
        }
        for p in data.personas
    ]

    user_flows = []
    for flow in data.user_flows:
        sorted_steps = sorted(flow.steps or [], key=lambda s: s.order_index)
        step_strs = []
        for step in sorted_steps:
            actor_prefix = f"{step.actor}: " if step.actor else ""
            step_strs.append(f"{actor_prefix}{step.description}")
        user_flows.append({"id": flow.id, "name": flow.name, "steps": step_strs})

    user_stories = []
    for i, s in enumerate(data.stories, start=1):
        user_stories.append({
            "id": f"US-{i:03d}",
            "actor": s.as_a,
            "action": s.i_want,
            "value": s.so_that,
            "acceptance_criteria": [ac.criterion for ac in (s.acceptance_criteria or [])],
            "priority": s.priority or "should",
            "dependencies": [],
        })

    functional_requirements = []
    for i, fr in enumerate(data.functional_requirements, start=1):
        story_ids = [link.story_id for link in (fr.story_links or [])]
        functional_requirements.append({
            "id": f"FR-{i:03d}",
            "description": fr.description,
            "inputs": list(fr.inputs or []),
            "outputs": list(fr.outputs or []),
            "related_user_stories": story_ids,
        })

    data_model = {
        "entities": [
            {
                "name": e.name,
                "attributes": list(e.attributes or []),
                "relationships": list(e.relationships or []),
            }
            for e in data.data_entities
        ]
    }

    business_rules = [
        {
            "id": r.id,
            "rule": r.rule,
            "applies_to": list(r.applies_to or []),
        }
        for r in data.business_rules
    ]

    llm_interaction_model = data.llm_interaction_model or {
        "llm_role": "",
        "interaction_pattern": "",
        "input_format": "",
        "output_format": "",
        "memory_strategy": "",
        "error_handling": [],
    }

    return {
        "project": data.project_name,
        "exported_at": now,
        "vision_scope": vision_scope,
        "personas": personas,
        "user_flows": user_flows,
        "user_stories": user_stories,
        "functional_requirements": functional_requirements,
        "data_model": data_model,
        "business_rules": business_rules,
        "llm_interaction_model": llm_interaction_model,
        "terminology": data.terminology,
    }


# ---------------------------------------------------------------------------
# arc42 Markdown export
# ---------------------------------------------------------------------------

_PLACEHOLDER = "> *Not yet captured.*"

_EXTERNAL_TYPES = {"gateway", "api", "cli", "external"}


def _placeholder_if_empty(lines: list[str]) -> str:
    return "\n".join(lines) if lines else _PLACEHOLDER


async def build_arc42(project_id: str, db: AsyncSession) -> str:
    loader = ExportDataLoader(db)
    data = await loader.load_arc42_export(project_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections: list[str] = []

    # Build once at the top so section 6 and section 10 share the same counts.
    # Unknown test_type values fall back to "unit" rather than creating phantom keys.
    _KNOWN_SPEC_TYPES = ("unit", "integration", "e2e")
    spec_by_type: dict[str, list] = {"unit": [], "integration": [], "e2e": []}
    for _sp in data.specs:
        bucket = _sp.test_type if _sp.test_type in _KNOWN_SPEC_TYPES else "unit"
        spec_by_type[bucket].append(_sp)

    # Header
    sections.append(f"# arc42 Architecture Documentation\n# {data.project_name}")
    sections.append(f"*Generated: {now}*\n\n---")

    # 1. Introduction and Goals
    purpose = data.problem_statement or _PLACEHOLDER
    # Quality goals: derive from must-have stories
    must_stories = [s for s in data.stories if (s.priority or "should") == "must"]
    qg_lines = [
        f"- {s.i_want} *(as a {s.as_a})*"
        for s in (must_stories or data.stories[:3])
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
    constraint_lines = [f"- **{c.type}**: {c.description}" for c in data.constraints]
    sections.append(f"## 2. Constraints\n\n{_placeholder_if_empty(constraint_lines)}")
    sections.append("---")

    # 3. System Context
    external = [
        c for c in data.components
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
    strategy_lines = [f"- **{d.title}**: {d.decision}" for d in data.decisions]
    sections.append(f"## 4. Solution Strategy\n\n{_placeholder_if_empty(strategy_lines)}")
    sections.append("---")

    # 5. Building Blocks
    component_blocks: list[str] = []
    for comp in data.components:
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
    for i, t in enumerate(data.tasks):
        task_lines.append(f"{i + 1}. **{t.title}** *(complexity: {t.complexity or 'medium'})*")
        if t.acceptance_criteria:
            for ac in t.acceptance_criteria:
                task_lines.append(f"   - {ac}")
    task_block = "\n".join(task_lines) if task_lines else _PLACEHOLDER

    spec_summary_lines = [
        f"- **Unit tests:** {len(spec_by_type['unit'])}",
        f"- **Integration tests:** {len(spec_by_type['integration'])}",
        f"- **End-to-end tests:** {len(spec_by_type['e2e'])}",
        f"- **Total:** {len(data.specs)}",
    ]

    sections.append(
        "## 6. Runtime View\n\n"
        "> *Sequence diagrams not yet generated.*\n\n"
        f"### Implementation Tasks ({len(data.tasks)})\n{task_block}\n\n"
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
    for sp in data.specs:
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
    for n, dec in enumerate(data.decisions, start=1):
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
    for story in data.stories:
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
        f"\n### Test Coverage\n{len(data.specs)} test spec{'s' if len(data.specs) != 1 else ''} defined"
        f" ({len(spec_by_type['unit'])} unit, {len(spec_by_type['integration'])} integration,"
        f" {len(spec_by_type['e2e'])} e2e)."
        if data.specs else ""
    )
    sections.append(
        f"## 10. Quality Requirements\n\n### Stories by Priority\n\n{quality_req_body}"
        f"{spec_count_line}"
    )
    sections.append("---")

    # 11. Risks and Technical Debt
    sections.append(f"## 11. Risks and Technical Debt\n\n{_PLACEHOLDER}")
    sections.append("---")

    # 12. Glossary — populated from BA terminology
    if data.terminology:
        gloss_lines = [f"- **{entry['term']}**: {entry['definition']}" for entry in data.terminology]
        glossary_body = "\n".join(gloss_lines)
    else:
        glossary_body = _PLACEHOLDER
    sections.append(f"## 12. Glossary\n\n{glossary_body}")

    return "\n\n".join(sections) + "\n"
