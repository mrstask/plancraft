# M6 — Pluggable exporters (spec-kit / Agent OS / OpenSpec)

**Duration:** 3 days
**Depends on:** M4 (per-feature directories), M5 (all artifact types available)
**Blocks:** —
**Status:** not started

## Goal

Refactor export to a pluggable interface. Ship four targets: the existing arc42 (refactored) plus three new ones — spec-kit, Agent OS, OpenSpec. Each target maps Plancraft's internal artifacts to the destination format's expected layout and passes a schema/lint check before being zipped.

## Why this milestone

Three popular agent frameworks (spec-kit, Agent OS, OpenSpec) each define their own project layout, and users downstream of Plancraft use one of them. Doing this as a proper interface makes adding a fifth or sixth target a half-day task.

## Interface

### `services/export/targets/base.py`

```python
from pathlib import Path
from typing import Protocol

class ExportTarget(Protocol):
    name: str                         # "arc42" | "spec-kit" | "agent-os" | "openspec"
    display_name: str
    description: str                  # shown in UI

    async def build(
        self,
        project_id: int,
        feature_ids: list[int] | None,    # None = all features
        out_dir: Path,
    ) -> "BuildResult": ...

class BuildResult:
    out_dir: Path
    files_written: list[Path]
    schema_valid: bool
    schema_errors: list[str]
```

Registration via a simple module-level list in `services/export/targets/__init__.py`.

### Export evaluator

After `build()`, a target-specific validator runs:

- **spec-kit:** check `.specify/specs/NNN/` has `spec.md`, `plan.md`, `tasks.md`; front-matter sanity.
- **Agent OS:** check `agent-os/standards/index.yml` references every file in `standards/`; check `product/mission.md` etc. exist.
- **OpenSpec:** check `openspec/changes/NNN/proposal.md` + `tasks.md` exist per change; validate `specs/*.md` have a capability heading.
- **arc42:** check all 12 sections present.

If validation fails, the exporter can either re-render (bounded retry) or surface the errors to the UI with the zip still produced but flagged invalid.

## Code changes

### Files created
- `services/export/targets/base.py` — protocol + `BuildResult`.
- `services/export/targets/arc42.py` — refactor of existing `services/export_service.py` into the new interface.
- `services/export/targets/spec_kit.py`.
- `services/export/targets/agent_os.py`.
- `services/export/targets/openspec.py`.
- `services/export/validators/` — one validator per target.

### Files modified
- `services/export_service.py` — becomes a thin orchestrator that picks a target and calls `build()` + validator.
- `routers/export.py` — list endpoint returns available targets; export endpoint accepts `target` query param; download returns zip + a `validation-report.json` sidecar.
- Templates: export dialog becomes a selector with description per target.

## Target-by-target mapping

### spec-kit → `.specify/`

| Plancraft artifact | spec-kit file |
|---|---|
| `Project.constitution_md` | `.specify/memory/constitution.md` |
| `product/mission.md` | `.specify/memory/product-mission.md` (supplementary) |
| Feature NNN BA stories + problem | `.specify/specs/NNN-slug/spec.md` |
| Feature NNN BA-clarifications | `.specify/specs/NNN-slug/research.md` |
| Feature NNN Architect plan | `.specify/specs/NNN-slug/plan.md` |
| Feature NNN data model | `.specify/specs/NNN-slug/data-model.md` |
| Feature NNN contracts | `.specify/specs/NNN-slug/contracts/*.md` |
| Feature NNN tasks | `.specify/specs/NNN-slug/tasks.md` |

### Agent OS → `agent-os/`

| Plancraft artifact | Agent OS file |
|---|---|
| Constitution rules | `agent-os/standards/*.md` (split by section) |
| `product/mission.md` | `agent-os/product/mission.md` (direct copy) |
| `product/roadmap.md` | `agent-os/product/roadmap.md` |
| `product/tech-stack.md` | `agent-os/product/tech-stack.md` |
| Features | `agent-os/specs/NNN-timestamp/` |
| Profile name + version | `agent-os/profile.txt` (informational) |

### OpenSpec → `openspec/`

| Plancraft artifact | OpenSpec file |
|---|---|
| Components / architectural capabilities | `openspec/specs/<capability>.md` |
| Each feature | `openspec/changes/NNN-slug/proposal.md` (why/what from BA + PM) + `tasks.md` (flattened DAG) + `design.md` (ADRs) |

### arc42 → existing

Unchanged content; refactored to live under the new interface.

## UI

- Export dialog: list of targets with description and "preview files" action (shows the file tree before zipping).
- After export: validation report summary — green tick or a list of warnings with the zip still downloadable.
- "Remember target" preference per project.

## Tests

- `tests/test_export_arc42.py` — refactored exporter produces same output as before (golden-file snapshot from current `services/export_service.py`).
- `tests/test_export_spec_kit.py` — full project → `.specify/` layout — fixture-based.
- `tests/test_export_agent_os.py` — same with `agent-os/`.
- `tests/test_export_openspec.py` — same with `openspec/`.
- `tests/test_export_validators.py` — invalid inputs produce expected error lists.
- Golden fixtures: one small canonical project with two features, full artifacts, used as input for every exporter.

## Exit criteria

- [ ] All four targets selectable in UI.
- [ ] Each target's validator runs and produces a report.
- [ ] Golden-file snapshots for all four targets, stable across runs.
- [ ] Existing arc42 export is byte-identical (or intentionally changed with a documented diff).
- [ ] README updated with matrix of what Plancraft exports to which tool.

## Risks

- **Target format drift.** Upstream tools (spec-kit especially) iterate quickly. Mitigation: version-pin each target to a specific upstream version (`spec_kit_v1.py`), document what version we match, add a note in the validator about the expected upstream commit hash or release.
- **Golden-file churn.** Small prompt changes upstream cause golden diffs on every model update. Mitigation: golden files compare structural keys (file presence, heading order) rather than full content.
- **Validation false positives.** Strict validators block legitimate exports. Mitigation: every validation error has a severity; warnings don't block, errors do. User can override with a checkbox.

## Out of scope

- Two-way sync (importing a spec-kit project back into Plancraft) → separate feature.
- Direct push to GitHub / creating a repo → separate feature.
- Target-specific slash-command file generation (`.claude/commands/`) → included for Agent OS and spec-kit by copying upstream's stubs; documented as optional.
