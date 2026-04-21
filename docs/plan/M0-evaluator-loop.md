# M0 — Evaluator loop scaffolding

**Duration:** 2–3 days
**Blocks:** all other milestones
**Status:** not started

## Goal

All role executions route through a `LoopController`. A `NullEvaluator` default keeps behavior identical to today. Iteration traces are persisted and visible in the UI. Later milestones plug real evaluators in without further refactoring.

## Why first

Every subsequent milestone adds a role or artifact that benefits from evaluator feedback. Retrofitting a loop into already-shipped roles means re-wiring call sites and context plumbing twice. Build the seam once, reuse six times.

## Concept

Each role becomes a **ReAct cycle**:

```
┌────────────┐   actor_output    ┌─────────────┐
│   Actor    │ ────────────────→ │  Evaluator  │
│  (LLM role)│                   │ (LLM judge) │
└────────────┘ ←──── critique ── └─────────────┘
      ↑                                  │
      └──── loop until score ≥ threshold ┘
                 or max_iterations reached
```

- **Actor** = the existing role (BA, PM, Architect, TDD, Reviewer, Founder).
- **Evaluator** = a lightweight LLM call (or deterministic check) that scores the actor's output against a rubric and emits a critique.
- **LoopController** decides: accept / retry with critique / escalate to user / hard-fail.

## New module: `services/llm/react_loop.py`

```python
from typing import Protocol, Literal

class EvaluationResult:
    score: float             # 0..1
    passed: bool             # score >= threshold
    critique: str            # feedback for next iteration
    missing_items: list[str]
    rubric_version: str

class ActorProtocol(Protocol):
    role: str
    async def run(self, context, critique: str | None) -> "ActorOutput": ...

class EvaluatorProtocol(Protocol):
    role: str
    rubric_source: Literal["global", "constitution", "feature"]
    async def evaluate(self, actor_output, context) -> EvaluationResult: ...

class LoopController:
    max_iterations: int = 3
    score_threshold: float = 0.8
    escalate_after: int = 2    # ask user after N failed iterations
    async def run(self, actor, evaluator, context) -> "RoleRunResult": ...

class RoleRunResult:
    final_artifacts: list
    trace: list["IterationTrace"]   # (iteration, actor_out, eval_score, critique)
    converged: bool
    escalated: bool
```

## Rubric layering

1. **Global defaults** in `services/llm/rubrics/<role>.yml` (shipped with the app).
2. **Constitution overrides** from `Project.constitution_md` (extracted rubric section).
3. **Feature overrides** from `specs/NNN/rubric.yml` (optional, per feature).

Later layers override earlier ones field-by-field. M0 ships the global layer only; M1 adds constitution layer; M4 adds feature layer.

## Null-evaluator default

M0 ships with `NullEvaluator` (always-pass, `score=1.0`). Every role runs through `LoopController.run()` from day one, but the loop exits after one iteration until a real evaluator replaces the default for that role. This is the "room" for future evaluators — architecture in place, filling is incremental.

## Data model changes

### New table: `role_execution_traces`

```sql
CREATE TABLE role_execution_traces (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    feature_id INTEGER NULL,                  -- populated from M4 onwards
    role VARCHAR(64) NOT NULL,
    iteration INTEGER NOT NULL,
    actor_prompt TEXT NOT NULL,
    actor_output TEXT NOT NULL,
    evaluator_score REAL NULL,
    evaluator_critique TEXT NULL,
    rubric_version VARCHAR(32) NULL,
    final BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_traces_project_role ON role_execution_traces(project_id, role, created_at);
```

Add to `models/db.py` and matching domain record in `models/domain.py`.

### Settings additions

New env vars (wire through `config.py`):

| Name | Default | Purpose |
|---|---|---|
| `EVALUATOR_ENABLED` | `false` | Master switch. False = all roles use NullEvaluator. |
| `EVALUATOR_MAX_ITERATIONS` | `3` | Hard cap on loop. |
| `EVALUATOR_SCORE_THRESHOLD` | `0.8` | Acceptance score. |
| `EVALUATOR_ESCALATE_AFTER` | `2` | Iterations before user prompt. |
| `EVALUATOR_MODEL` | `gemma4:latest` | Model to use for judge LLM. |
| `TRACE_RETENTION_DAYS` | `30` | Prune traces older than N days (non-final only). |

## Code changes

### Files created
- `services/llm/react_loop.py` — controller + protocols.
- `services/llm/evaluators/__init__.py` — empty registry, filled in M1+.
- `services/llm/evaluators/null_evaluator.py` — always-pass.
- `services/llm/rubrics/__init__.py` + `services/llm/rubrics/<role>.yml` (one stub per existing role).

### Files modified
- `roles/base.py` — extract the existing actor call into `ActorProtocol`; add a `run_with_loop(role, context)` helper that: resolves evaluator from registry, builds rubric, calls `LoopController.run`, persists trace, returns artifacts.
- `roles/business_analyst.py`, `roles/product_manager.py`, `roles/architect.py`, `roles/tdd_tester.py`, `roles/reviewer.py`, `roles/ba_clarifications.py` — swap their direct-LLM call site for `run_with_loop`. No behavior change with NullEvaluator.
- `models/db.py`, `models/domain.py` — new `role_execution_traces` table + domain record.
- `services/knowledge/commands.py` — add `persist_iteration_trace(...)`.
- `services/knowledge/queries.py` — add `get_traces_for_turn(project_id, role, since)`.
- `config.py` — new env vars.
- `routers/docs.py` or a new `routers/traces.py` — endpoint to fetch traces for a given role turn (for the UI panel).
- `templates/partials/knowledge_panel.html` — add a collapsible "Iteration trace" section shown below each role turn.

## UI

Collapsible panel rendered below every completed role turn:

```
BA · 1/1 iterations ✓
  └─ 1  score 1.00 ✓ accepted
      artifacts: 4 stories, 2 constraints
```

With NullEvaluator the panel is minimal. The component is reused in M1+ once real evaluators produce multi-iteration traces.

## Tests

Add to `tests/`:

- `tests/test_react_loop.py`
  - `LoopController` converges on pass-first-try (NullEvaluator).
  - `LoopController` retries up to `max_iterations` when evaluator fails.
  - `LoopController` escalates after `escalate_after`.
  - Trace rows contain all iterations with monotonic `iteration` values and exactly one `final=True` row.
- `tests/test_trace_persistence.py`
  - Round-trip via `persist_iteration_trace` and `get_traces_for_turn`.
  - Trace scoped to correct project.
- Regression: all existing phase-gating and role tests still pass unchanged.

## Migration

One Alembic / SQL migration adding `role_execution_traces`. No backfill needed.

## Exit criteria

- [ ] `EVALUATOR_ENABLED=false` is the default; behavior identical to today.
- [ ] Every role call produces at least one `role_execution_traces` row with `final=True`.
- [ ] `tests/test_react_loop.py` covers convergence / retry / escalation paths.
- [ ] UI shows a "1/1 iterations ✓" panel after each role turn.
- [ ] No changes to role prompts themselves in this milestone.

## Risks

- **Prompt drift.** Refactoring role call sites can subtly change the prompt (whitespace, ordering). Snapshot-test the final prompt before and after the refactor to catch this.
- **Trace volume.** Even with NullEvaluator, one row per role turn adds up. Prune job driven by `TRACE_RETENTION_DAYS` is optional in M0 (doc-only); implement in M1 once row shape is proven.
- **Async plumbing.** `LoopController.run` must respect the existing async boundaries in `roles/base.py`. Keep the signature async throughout.

## Out of scope (explicitly deferred)

- Real evaluators → M1 onwards.
- Constitution-driven rubric overrides → M1.
- Feature-scoped traces → M4 (the `feature_id` column is added in M0 as nullable to avoid a later migration).
- UI for editing rubrics → later; rubrics are file-system only in M0.
