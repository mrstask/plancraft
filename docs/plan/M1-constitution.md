# M1 — Constitution artifact + first real evaluator

**Duration:** 2 days
**Depends on:** M0
**Blocks:** M3 (profiles seed their initial constitution from this)
**Status:** not started

## Goal

Constitution is a first-class, DB-backed, per-project artifact. The Reviewer role consumes it. The first real evaluator (Reviewer's evaluator) checks output against constitution rules and drives re-runs until compliant or escalated.

## Why this milestone

Plancraft's Reviewer already performs implicit consistency checks. Making the rules explicit as a constitution does three things at once:

1. Gives users a single place to state project-wide principles (testing philosophy, non-functional defaults, naming, error-handling style).
2. Gives the Reviewer evaluator a concrete rubric rather than an implicit one.
3. Produces an artifact that both Agent OS and spec-kit want. Exports in M6 become cheaper.

## Data model

### Migration

```sql
ALTER TABLE projects ADD COLUMN constitution_md TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN profile_ref VARCHAR(128) NULL;  -- used by M3
```

Update `models/domain.py` `Project` record. Backfill: on app start, for any project with empty `constitution_md`, seed from `services/workspace/templates/default_constitution.md`.

### Default constitution template

New file `services/workspace/templates/default_constitution.md`. Minimum sections:

```markdown
# Constitution

## Quality rules
- All user stories must have at least one acceptance criterion.
- All components must be referenced by at least one story.

## Testing
- Every user story requires at least one Given/When/Then test spec.

## Non-functional defaults
- (add NFR defaults the project inherits unless overridden)

## Naming
- (naming conventions)
```

The template is deliberately small. Users edit it; profiles (M3) replace it wholesale.

## Code changes

### Files created
- `services/workspace/templates/default_constitution.md`
- `services/workspace/renderers/constitution.py` — writes `.plancraft/constitution.md` from `Project.constitution_md`.
- `services/llm/evaluators/reviewer_evaluator.py` — the first real evaluator.
- `services/llm/rubrics/reviewer.yml` — fleshed out (stubbed in M0).

### Files modified
- `models/db.py`, `models/domain.py` — new fields on `Project`.
- `services/workspace/workspace.py` — invoke new renderer.
- `services/workspace/role_context.py` — inject constitution into Reviewer's context (and, optionally, shortened summary into other roles).
- `roles/reviewer.py` — prompt additions referencing constitution rules.
- `routers/docs.py` — GET/PUT endpoints for project constitution (HTMX swap).
- `templates/partials/knowledge_panel.html` — new "Constitution" tab with a markdown editor.
- `services/llm/evaluators/__init__.py` — register `ReviewerEvaluator` under role `"reviewer"`.

## Reviewer evaluator design

Rubric extraction:

1. Parse the constitution markdown. Under each `## <Section>` heading, collect bullet items starting with `-`.
2. Each bullet becomes a rule: `{section, text, severity: warn|block}`. Severity defaults to `block` for explicit "must" language, `warn` otherwise.

Evaluation call:

1. Build a judge prompt: "Given these rules and this Reviewer output, list which rules (if any) are violated. For each violation: rule text, violating artifact id, one-sentence critique."
2. Parse the structured response. `score = 1 - (blocked_violations / total_rules)`. Passes if no blocked violations.
3. Critique returned to the actor is a bullet list of violations.

Evaluator uses `EVALUATOR_MODEL` (default `gemma4:latest`), not the Reviewer's own model. Keep the context tight: constitution + Reviewer output only, no full project state.

## UI

- New tab in project view: **Constitution**. Simple markdown editor (textarea + preview). Save via HTMX.
- Iteration trace panel (already built in M0) now regularly shows 2–3 iterations for Reviewer turns when rules fail.
- On escalation: modal shows the critique and offers "accept anyway" / "edit constitution" / "retry manually".

## Tests

- `tests/test_constitution.py`
  - Round-trip: write constitution → render file → read back.
  - Default constitution applied on project create.
  - Rubric parser: markdown with mixed headings and bullets produces expected rules list.
- `tests/test_reviewer_evaluator.py`
  - Violating output triggers retry with critique injected into next actor call.
  - Non-violating output passes in one iteration.
  - Escalation after `escalate_after` iterations.
- `tests/test_phase_status.py` — ensure Reviewer phase still gates correctly when evaluator retries.

## Migration

- Migration adds the two columns with defaults.
- Startup task backfills empty `constitution_md` from the template.

## Exit criteria

- [ ] Every project has a non-empty constitution at any point after creation.
- [ ] User can edit the constitution via UI and changes land in DB + rendered file.
- [ ] With `EVALUATOR_ENABLED=true` and a rule-violating state, Reviewer re-runs up to `max_iterations` and converges or escalates.
- [ ] Exported workspace zip includes `.plancraft/constitution.md`.

## Risks

- **Rubric format brittleness.** Free-form markdown is easy for users but hard to parse robustly. Mitigation: parser is lenient (unknown section → still collects bullets; malformed bullet → skipped with warning in trace).
- **Prompt tokens.** Constitution plus reviewer context may be large. Mitigation: truncate constitution to first N bullets per section when context budget is tight; log a warning in the trace.
- **Evaluator judges itself.** Judge LLM can mis-read violations. Mitigation: threshold is project-configurable via env; defaults favor fewer false blocks.

## Out of scope

- Constitution version history → later; overwrites are fine for v1.
- Evaluators for other roles → M2 (Founder), M4 (BA/Architect/TDD scoped).
- Cross-project constitution reuse → M3.
