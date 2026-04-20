"""arc42 per-section renderer.

Each public function writes exactly one arc42 section file and returns its Path.
All functions are idempotent — they overwrite on every call.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.export.queries import Arc42ExportData
    from services.workspace.workspace import ProjectWorkspace

_PLACEHOLDER = "> *Not yet captured.*"
_EXTERNAL_TYPES = {"gateway", "api", "cli", "external"}
_KNOWN_SPEC_TYPES = ("unit", "integration", "e2e")


def _ph(lines: list[str]) -> str:
    return "\n".join(lines) if lines else _PLACEHOLDER


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _spec_buckets(specs) -> dict[str, list]:
    buckets: dict[str, list] = {"unit": [], "integration": [], "e2e": []}
    for sp in specs:
        bucket = sp.test_type if sp.test_type in _KNOWN_SPEC_TYPES else "unit"
        buckets[bucket].append(sp)
    return buckets


# ---------------------------------------------------------------------------
# Individual section writers
# ---------------------------------------------------------------------------

def render_01_introduction(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    purpose = data.problem_statement or _PLACEHOLDER
    must_stories = [s for s in data.stories if (s.priority or "should") == "must"]
    qg_lines = [
        f"- {s.i_want} *(as a {s.as_a})*"
        for s in (must_stories or data.stories[:3])
    ]
    adr_rel = "../../docs/adr/"
    content = (
        "# 1. Introduction and Goals\n\n"
        f"### Purpose\n{purpose}\n\n"
        f"### Quality Goals\n{_ph(qg_lines)}\n\n"
        "### Stakeholders\n> *Not yet captured.*\n\n"
        "---\n"
        f"*See [Architecture Decisions]({adr_rel}) for recorded ADRs.*\n"
    )
    path = ws.arc42_section(1, "introduction")
    path.write_text(content, encoding="utf-8")
    return path


def render_02_constraints(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    lines = [f"- **{c.type}**: {c.description}" for c in data.constraints]
    content = f"# 2. Constraints\n\n{_ph(lines)}\n"
    path = ws.arc42_section(2, "constraints")
    path.write_text(content, encoding="utf-8")
    return path


def render_03_context(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    external = [
        c for c in data.components
        if (c.component_type or "").lower() in _EXTERNAL_TYPES
    ]
    ext_block = (
        "\n".join(f"- **{c.name}** ({c.component_type}): {c.responsibility}" for c in external)
        if external else _PLACEHOLDER
    )
    c4_rel = "../c4/workspace.dsl"
    content = (
        "# 3. System Context\n\n"
        f"> *See [{c4_rel}]({c4_rel}) — System Context view.*\n\n"
        f"### External Interfaces\n{ext_block}\n"
    )
    path = ws.arc42_section(3, "context")
    path.write_text(content, encoding="utf-8")
    return path


def render_04_solution_strategy(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    adr_rel = "../adr/"
    lines = [f"- **{d.title}**: {d.decision}  →  [ADR]({adr_rel})" for d in data.decisions]
    content = f"# 4. Solution Strategy\n\n{_ph(lines)}\n"
    path = ws.arc42_section(4, "solution_strategy")
    path.write_text(content, encoding="utf-8")
    return path


def render_05_building_blocks(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    blocks: list[str] = []
    for comp in data.components:
        lines = [
            f"### {comp.name}",
            f"**Type:** {comp.component_type or '–'}",
            f"**Responsibility:** {comp.responsibility}",
        ]
        if comp.file_paths:
            paths = ", ".join(f"`{p}`" for p in comp.file_paths)
            lines.append(f"**Files:** {paths}")
        blocks.append("\n".join(lines))

    c4_rel = "../c4/workspace.dsl"
    body = "\n\n".join(blocks) if blocks else _PLACEHOLDER
    content = (
        "# 5. Building Blocks\n\n"
        f"> *Component diagram: [{c4_rel}]({c4_rel}) — Container/Component views.*\n\n"
        f"{body}\n"
    )
    path = ws.arc42_section(5, "building_blocks")
    path.write_text(content, encoding="utf-8")
    return path


def render_06_runtime(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    spec_buckets = _spec_buckets(data.specs)
    task_lines: list[str] = []
    for i, t in enumerate(data.tasks):
        task_lines.append(f"{i + 1}. **{t.title}** *(complexity: {t.complexity or 'medium'})*")
        for ac in (t.acceptance_criteria or []):
            task_lines.append(f"   - {ac}")

    spec_summary = (
        f"- **Unit:** {len(spec_buckets['unit'])}\n"
        f"- **Integration:** {len(spec_buckets['integration'])}\n"
        f"- **E2E:** {len(spec_buckets['e2e'])}\n"
        f"- **Total:** {len(data.specs)}"
    )
    tasks_rel = "../../tasks/tasks.json"
    content = (
        "# 6. Runtime View\n\n"
        "> *Sequence diagrams not yet generated.*\n\n"
        f"### Implementation Tasks ({len(data.tasks)})\n\n"
        f"{_ph(task_lines)}\n\n"
        f"*Full task DAG: [{tasks_rel}]({tasks_rel})*\n\n"
        f"### Test Coverage Summary\n\n{spec_summary}\n"
    )
    path = ws.arc42_section(6, "runtime")
    path.write_text(content, encoding="utf-8")
    return path


def render_07_deployment(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    content = "# 7. Deployment View\n\n> *Deployment diagram not yet generated.*\n"
    path = ws.arc42_section(7, "deployment")
    path.write_text(content, encoding="utf-8")
    return path


def render_08_crosscutting(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    specs_rel = "../../tests/specs/"
    spec_blocks: list[str] = []
    for i, sp in enumerate(data.specs):
        lines = [f"#### SPEC-{i + 1:03d}: {sp.description}", f"**Type:** {sp.test_type or 'unit'}"]
        if sp.given_context:
            lines.append(f"**Given:** {sp.given_context}")
        if sp.when_action:
            lines.append(f"**When:** {sp.when_action}")
        if sp.then_expectation:
            lines.append(f"**Then:** {sp.then_expectation}")
        lines.append(f"\n*File: [{specs_rel}SPEC-{i + 1:03d}.md]({specs_rel}SPEC-{i + 1:03d}.md)*")
        spec_blocks.append("\n".join(lines))

    catalogue = "### Test Specifications\n\n" + "\n\n".join(spec_blocks) if spec_blocks else _PLACEHOLDER
    content = f"# 8. Cross-cutting Concepts\n\n{catalogue}\n"
    path = ws.arc42_section(8, "crosscutting")
    path.write_text(content, encoding="utf-8")
    return path


def render_09_decisions(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    adr_rel = "../adr/"
    adr_index_lines: list[str] = []
    for n, dec in enumerate(data.decisions, start=1):
        slug = _slug(dec.title)
        fname = f"{n:04d}-{slug}.md"
        adr_index_lines.append(f"- [ADR-{n:04d}: {dec.title}]({adr_rel}{fname})")

    body = "\n".join(adr_index_lines) if adr_index_lines else _PLACEHOLDER
    content = (
        "# 9. Architecture Decisions\n\n"
        f"> Individual ADRs are in [{adr_rel}]({adr_rel}).\n\n"
        f"## Index\n\n{body}\n"
    )
    path = ws.arc42_section(9, "decisions")
    path.write_text(content, encoding="utf-8")
    return path


def render_10_quality(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    spec_buckets = _spec_buckets(data.specs)
    priority_order = ["must", "should", "could", "wont"]
    by_priority: dict[str, list] = defaultdict(list)
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

    quality_body = "\n".join(story_sections) if story_sections else _PLACEHOLDER
    spec_line = (
        f"\n### Test Coverage\n{len(data.specs)} spec(s): "
        f"{len(spec_buckets['unit'])} unit, {len(spec_buckets['integration'])} integration, "
        f"{len(spec_buckets['e2e'])} e2e."
        if data.specs else ""
    )
    content = (
        "# 10. Quality Requirements\n\n"
        f"### Stories by Priority\n\n{quality_body}"
        f"{spec_line}\n"
    )
    path = ws.arc42_section(10, "quality")
    path.write_text(content, encoding="utf-8")
    return path


def render_11_risks(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    content = "# 11. Risks and Technical Debt\n\n> *Not yet captured.*\n"
    path = ws.arc42_section(11, "risks")
    path.write_text(content, encoding="utf-8")
    return path


def render_12_glossary(ws: "ProjectWorkspace", data: "Arc42ExportData") -> Path:
    content = "# 12. Glossary\n\n> *Not yet captured.*\n"
    path = ws.arc42_section(12, "glossary")
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Render all sections at once
# ---------------------------------------------------------------------------

ALL_SECTION_RENDERERS = [
    render_01_introduction,
    render_02_constraints,
    render_03_context,
    render_04_solution_strategy,
    render_05_building_blocks,
    render_06_runtime,
    render_07_deployment,
    render_08_crosscutting,
    render_09_decisions,
    render_10_quality,
    render_11_risks,
    render_12_glossary,
]


def render_all(ws: "ProjectWorkspace", data: "Arc42ExportData") -> list[Path]:
    return [fn(ws, data) for fn in ALL_SECTION_RENDERERS]
