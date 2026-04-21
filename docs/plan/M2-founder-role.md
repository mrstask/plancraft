# M2 — Founder role + product triad

**Duration:** 2–3 days
**Depends on:** M0 (for the evaluator loop). M1 optional but recommended (evaluator rubrics overlap).
**Blocks:** — (independent of M3/M4)
**Status:** not started

## Goal

`product/mission.md`, `product/roadmap.md`, `product/tech-stack.md` become three separate, first-class artifacts produced by a new `Founder` role that runs at project start. Each is backed by typed DB records rather than generated on the fly.

## Why this milestone

Today Plancraft's BA and PM phases implicitly produce this content, scattered across stories, epics, and component decisions. Splitting them out gives:

- A proper project-framing step that other roles cite explicitly.
- Direct compatibility with Agent OS's `product/` directory and spec-kit's product planning section (M6 becomes a trivial path map).
- A clean layer for a Founder evaluator (rubric: mission specificity, roadmap coverage, tech-stack rationale).

## Data model

### New tables

```sql
CREATE TABLE project_missions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    statement TEXT NOT NULL,
    target_users TEXT NOT NULL,
    problem TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_roadmap_items (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    title VARCHAR(256) NOT NULL,
    description TEXT NOT NULL,
    linked_epic_id INTEGER NULL,               -- fills in once PM runs
    mvp BOOLEAN NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tech_stack_entries (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    layer VARCHAR(64) NOT NULL,                 -- "backend", "frontend", "storage", etc.
    choice VARCHAR(256) NOT NULL,
    rationale TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Add matching domain records and CRUD in `services/knowledge/`.

## Code changes

### Files created
- `roles/founder.py` — new role. Inputs: initial project description (from user + BA problem statement). Outputs: mission fields, roadmap items (without `linked_epic_id` at this point), tech-stack entries.
- `services/workspace/renderers/mission.py`, `roadmap.py`, `tech_stack.py` — one per file.
- `services/llm/evaluators/founder_evaluator.py`.
- `services/llm/rubrics/founder.yml`.

### Files modified
- `roles/__init__.py` — register `Founder`.
- `services/workspace/workspace.py` — invoke three new renderers.
- `services/workspace/role_context.py` — include mission + roadmap + tech-stack summaries in every role's context.
- Phase gating: extend `services/workspace/` (wherever phase order is defined) to insert Founder before BA. The new order: `Founder → BA → BA-clarify → PM → Architect → TDD → Reviewer`.
- Routers: add `routers/founder.py` or extend an existing one with founder-turn endpoints.
- Templates: the project view's phase tabs gain a **Founder** tab (first).
- PM role: once it produces epics, back-link each roadmap item to its epic via `linked_epic_id`. This is the only cross-phase change.

## Founder evaluator

Rubric (ships in `services/llm/rubrics/founder.yml`):

- **Mission specificity:** statement must be ≤ 2 sentences, must name the user and the outcome. Lint rule: no empty `target_users` or `problem`.
- **Roadmap coverage:** every high-level goal in the mission must have at least one roadmap item whose description references the goal keyword.
- **Tech-stack rationale:** every entry has a non-empty `rationale` longer than 40 chars.
- **MVP flag sanity:** at least one roadmap item is flagged `mvp=1`.

Score: fraction of rules passed. Threshold from env (`EVALUATOR_SCORE_THRESHOLD`).

## UI

- New **Founder** tab before BA in the project view.
- Three side-by-side cards in that tab: Mission, Roadmap, Tech stack. Each editable via HTMX PATCH.
- Phase-gate: BA tab stays locked until all three have content and Founder's evaluator has passed (or been accepted on escalation).

## Legacy project migration

Existing projects have no mission/roadmap/tech-stack records. Two options, user picks at upgrade:

1. **Run Founder retroactively** on the project's existing BA problem statement (async job, produces draft artifacts).
2. **Manual entry** — empty records, user fills.

Default on first open of a legacy project: show a banner offering option 1, fall back to option 2 if declined.

## Tests

- `tests/test_founder.py`
  - Founder produces mission + ≥1 roadmap item + ≥1 tech-stack entry.
  - Phase gate blocks BA until Founder artifacts exist.
  - Legacy-project migration path: BA-only project seeded with draft founder artifacts.
- `tests/test_founder_evaluator.py`
  - Missing rationale triggers retry.
  - No-MVP roadmap triggers retry.
- `tests/test_workspace_renderer.py` — three new files present in rendered workspace.
- Regression: existing BA/PM/Architect tests still pass with Founder ahead of them.

## Exit criteria

- [ ] New projects go through Founder before BA, producing the three files.
- [ ] Legacy projects either run the retroactive Founder or accept manual entry.
- [ ] PM back-links roadmap items to epics in at least 90% of cases; orphans flagged by the Reviewer.
- [ ] Exported workspace contains `product/mission.md`, `product/roadmap.md`, `product/tech-stack.md`.
- [ ] Founder evaluator demonstrably re-runs when rubric fails.

## Risks

- **Overlap with BA.** Founder and BA both discuss "problem" and "users." Guard: Founder outputs are short and declarative (the framing); BA outputs are detailed stories. Different tables + different prompts reduce overlap but some redundancy remains — acceptable.
- **Legacy migration noise.** Retroactive Founder may produce draft artifacts users don't trust. Banner copy must make draft-nature clear and require explicit acceptance.
- **Phase gate UX.** Inserting a new gate at the front can surprise existing users. Soft gate (warning only) for legacy projects, hard gate for new projects.

## Out of scope

- Profile inheritance of tech-stack defaults → M3.
- Roadmap-item-to-feature binding → M4 (roadmap items become the queue of features).
- Editing UI for arbitrary roadmap reordering → v2.
