# M4 — Feature entity and iterative feature loop

**Duration:** 5–7 days
**Depends on:** M0 (must-have). M1/M2 recommended.
**Blocks:** M5, M6
**Status:** not started

## Goal

A project contains many features. Each feature has its own `specs/NNN-slug/` directory and its own scoped spec → plan → tasks → review loop. After shipping feature 001, the user returns and runs the same flow for feature 002 against the existing project state.

**This is the biggest structural change in the plan.** It converts Plancraft from one-shot greenfield to a long-lived iterative planning companion.

## Why this milestone

Today one project = one plan. That is a hard ceiling for anyone who wants to extend a plan after partial implementation. The spec-kit iteration model (numbered feature folders) is the minimal shape that unlocks this without throwing away the project-level artifacts Plancraft is good at.

## Decide before starting

Confirm the product direction. If users will **not** return to projects after the first implementation hand-off, skip M4 and stop at M3. Everything downstream (M5, M6) still has value, but the project-level artifacts would ship without feature scoping.

## Data model

### New table

```sql
CREATE TABLE features (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    slug VARCHAR(128) NOT NULL,               -- URL-safe
    ordinal INTEGER NOT NULL,                 -- 1, 2, 3 … for NNN prefix
    title VARCHAR(256) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'drafting',  -- drafting | ready | in_progress | done | archived
    roadmap_item_id INTEGER NULL REFERENCES project_roadmap_items(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, slug),
    UNIQUE(project_id, ordinal)
);
```

### Scope columns on existing tables

Add nullable `feature_id` FK to:
- `user_stories`
- `test_specs`
- `tasks`
- `adrs`
- `interface_contracts` (from M5 — add now so we don't migrate twice)

`NULL` = project-level / cross-cutting. Non-NULL = scoped to that feature.

The `role_execution_traces.feature_id` column from M0 is now populated.

## Backfill migration (highest-risk item in the plan)

For each existing project:

1. Create a synthetic feature `001-initial` with `status='done'`.
2. Set `feature_id` to that feature on every existing `user_stories`, `test_specs`, `tasks`, `adrs` row belonging to the project.
3. Leave `adrs` that look cross-cutting (heuristic: marked as architecture-level or referenced by ≥2 epics) at `feature_id = NULL`.

Requirements:
- Dry-run mode prints counts and proposed changes without committing.
- Single transaction per project.
- Reversible: keep the pre-migration row counts and a rollback script.
- Feature flag: `FEATURE_SCOPING_ENABLED=false` lets the migration run but app continues in single-feature mode until flipped.

## Code changes

### Files created
- `services/features/` — package with `commands.py`, `queries.py`, `renderer.py`.
- `services/workspace/renderers/spec.py`, `plan.py`, `tasks.py`, `data_model.py` — per-feature files rendered into `specs/NNN-slug/`.
- `services/llm/evaluators/ba_feature_evaluator.py`
- `services/llm/evaluators/architect_feature_evaluator.py`
- `services/llm/evaluators/tdd_feature_evaluator.py`
- `services/llm/rubrics/ba_feature.yml`, `architect_feature.yml`, `tdd_feature.yml`.
- `routers/features.py` — feature CRUD + per-feature chat endpoints.
- `templates/features/` — feature list, feature detail (phase-gated tabs scoped to the feature).

### Files modified
- `models/db.py`, `models/domain.py` — new `Feature` record, new FKs on existing records.
- `services/workspace/workspace.py` — emit `specs/NNN-slug/` per feature.
- `services/workspace/role_context.py` — context assembly gains a feature dimension:
  - Global constitution (always).
  - Project-level artifacts (always — mission, roadmap, tech-stack, cross-cutting ADRs).
  - **This feature's** artifacts (always).
  - **Summary** of prior features — title + one-liner + status only. Never full content.
- `services/knowledge/queries.py` — every query gains an optional `feature_id` filter. Cross-cutting queries pass `feature_id=None`.
- All role files — accept a `feature: Feature | None` argument and filter context accordingly. Founder, PM, and cross-cutting reviewer runs keep `feature=None`.
- Phase gating: extended to work per feature. A feature's BA tab locks until the feature exists; its Architect tab locks until BA produces ≥1 story; and so on, independently of other features.

## Workflow: two loops

**Project loop (once per project, roles scoped to `feature=None`):**
`Founder → BA (problem framing) → PM (epics + MVP) → Architect (cross-cutting ADRs + component map) → Reviewer (constitution compliance on project-level state)`

**Feature loop (once per feature, roles scoped to `feature=F`):**
`BA (feature stories) → BA-clarify (research.md) → Architect (feature plan + data-model + contracts) → TDD (feature tasks) → Reviewer (feature + constitution)`

The project loop is a one-time setup. The feature loop runs per feature and is where evaluators fire most often.

## Feature-scoped evaluators

Now that outputs are smaller (one feature's worth), evaluators become much more effective:

- **BA-feature:** every story has acceptance criteria; every story links to a roadmap item; no duplicate stories within the feature.
- **Architect-feature:** every epic touched has ≥1 component; every story touches ≥1 component; data-model entities referenced by ≥1 story.
- **TDD-feature:** every story has ≥1 test spec; task DAG is connected, no orphans, no cycles; every task maps to a test spec.

Each evaluator gets a YAML rubric. All three go through `LoopController` from M0.

## UI

- **Features list** inside project: table with ordinal, title, status. "New feature" button.
- **Feature detail**: phase-gated tabs (BA / Clarify / Architect / TDD / Reviewer), scoped to this feature.
- **Project-level tabs** remain (Founder, PM, cross-cutting Architect, project Reviewer) but are effectively "read-only after the project loop completes" — editable if re-opened.
- **Switcher**: breadcrumb `Project > Feature 002` with quick jump to sibling features.

## Tests

- `tests/test_feature_entity.py` — CRUD, unique constraints, cascading delete.
- `tests/test_backfill_migration.py` — dry-run matches actual migration; idempotent; rollback works.
- `tests/test_feature_scoped_queries.py` — artifacts isolate by `feature_id`; cross-cutting visible everywhere.
- `tests/test_feature_phase_gating.py` — feature 002 BA opens without feature 001 being done.
- `tests/test_feature_evaluators.py` — each evaluator fires correctly on its rubric.
- `tests/test_workspace_feature_rendering.py` — `specs/001-slug/` contents match scoped artifacts.
- Regression: all prior tests pass, in particular the Founder and Constitution tests from M1/M2.

## Migration plan (operational)

1. Ship migration code behind `FEATURE_SCOPING_ENABLED=false`. App still works in single-feature mode.
2. Run dry-run in staging against real data.
3. Flip flag to `true`, run migration, app shows `features` tab.
4. Monitor for a week; keep rollback script handy.
5. Remove the flag and the pre-M4 code paths in a follow-up.

## Exit criteria

- [ ] Existing projects look unchanged: one feature `001-initial` holding all prior artifacts.
- [ ] New feature 002 can be created, spec'd, and shipped independently.
- [ ] Role context respects feature scope + global constitution + prior-feature summaries.
- [ ] `specs/NNN-slug/` directories render and export correctly.
- [ ] Feature-scoped evaluators demonstrably reduce ambiguity (measured: fewer Reviewer-phase issues per feature compared to pre-M4 baseline).

## Risks

- **Backfill correctness.** Highest-risk step in the plan. Dry-run, transactional, reversible, shipped behind a flag. No exceptions.
- **Context budget blowup.** Cross-cutting ADRs + constitution + feature context may exceed local-model windows. Mitigation: a "summary view" for cross-cutting artifacts, enabled when `prompt_tokens > budget * 0.8`.
- **Feature ordinal gaps on delete.** Deleting feature 003 leaves an ordinal gap. Decision: allow gaps, never renumber — matches git-style branch numbering.
- **Two loops confusing users.** The project vs feature distinction needs clear UI cues. Mitigation: banner on first post-migration load explaining the two loops; breadcrumb at all times.

## Out of scope

- Feature dependencies (feature 003 depends on 002 being done) → v2 if users ask.
- Feature branching / parallel features in separate git branches → separate feature request.
- Auto-promotion of a feature's artifacts into cross-cutting state → manual in v1.
