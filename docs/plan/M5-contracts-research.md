# M5 — contracts/, research.md, per-feature ADRs polish

**Duration:** 2 days
**Depends on:** M4 (per-feature directory structure must exist)
**Blocks:** M6 (exporters need these artifacts to produce full output)
**Status:** not started

## Goal

Close the last spec-kit content gaps. Add three small artifact types so Plancraft matches the richest per-feature output formats of any agent framework.

## Artifacts added

1. **`contracts/`** — explicit interface / API / event contracts per component boundary, one file per contract.
2. **`research.md`** — the raw BA-clarifications Q&A, persisted alongside the stories it informed.
3. **Per-feature ADRs** — ADRs with `feature_id` set render into `specs/NNN/adrs/` instead of `architecture/adrs/`.

## Data model

### New table

```sql
CREATE TABLE interface_contracts (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    feature_id INTEGER NULL REFERENCES features(id) ON DELETE CASCADE,  -- M4 col
    component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    kind VARCHAR(32) NOT NULL,          -- "rest" | "graphql" | "event" | "function" | "cli"
    name VARCHAR(256) NOT NULL,
    body_md TEXT NOT NULL,               -- full markdown (shape, examples, errors)
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_contracts_feature ON interface_contracts(feature_id);
```

(`feature_id` column already exists on this table from M4's anticipatory migration.)

### Research persistence

No new table. Use the existing clarifications storage and extend its renderer. Schema today stores Q&A pairs; we just start rendering them to disk instead of only folding them into stories.

### ADR rendering split

ADRs already have `feature_id` (M4). Renderer reads it and places the file accordingly. No model changes.

## Code changes

### Files created
- `services/workspace/renderers/contracts.py` — reads `interface_contracts` for the feature, writes `specs/NNN/contracts/<kind>-<slug>.md` per contract.
- `services/workspace/renderers/research.py` — reads BA-clarifications for the feature, writes `specs/NNN/research.md`.
- `services/workspace/renderers/adrs_split.py` — replaces/extends current ADR rendering; splits feature-local vs cross-cutting.

### Files modified
- `roles/architect.py` — prompt adds contract extraction. For each component the Architect touches in a feature, elicit at minimum one contract (if the component has any external interface). Keep existing component output intact.
- `services/knowledge/commands.py`, `queries.py` — contract CRUD + lookups.
- `services/workspace/workspace.py` — invoke new renderers; route ADRs through `adrs_split`.
- `roles/ba_clarifications.py` — no logic change, but verify output is structured enough for the renderer (Q/A fields).

## Contract output format

Each contract is a standalone markdown file with a consistent header:

```markdown
# Contract: CreateOrder (REST)

- **Kind:** rest
- **Component:** orders-service
- **Feature:** 002-payment-integration

## Request
POST /orders
Body:
  { "user_id": uuid, "items": [ { "sku": string, "qty": int } ] }

## Response 201
  { "order_id": uuid, "status": "pending" }

## Errors
- 400 invalid_items
- 402 payment_required

## Examples
(…)
```

The Architect's prompt includes this template. The renderer does not format — it just writes what the Architect produced, trusting the role.

## UI

- Inside a feature's Architect tab: new "Contracts" panel beside the component list. Each contract is a card showing kind + name + component, click to open a markdown editor.
- Inside BA-clarify tab: "Research log" panel showing the Q&A list, read-only except for an "edit this answer" inline action.
- ADRs panel inside a feature: filtered by `feature_id`; a toggle reveals the project-level cross-cutting ADRs in a different color.

## Tests

- `tests/test_contracts.py` — CRUD; Architect role produces contracts when components have external interfaces.
- `tests/test_research_rendering.py` — clarifications round-trip to `specs/NNN/research.md`.
- `tests/test_adr_split_rendering.py` — feature-local and cross-cutting ADRs render to correct paths.
- Regression: existing component + ADR + clarifications tests still pass.

## Exit criteria

- [ ] Every feature whose components have external interfaces has at least one contract file.
- [ ] `specs/NNN/research.md` is present whenever BA-clarify ran for that feature.
- [ ] ADRs appear in exactly one place — either feature folder or project folder — never both.
- [ ] Exported workspace zip contains the new files.

## Risks

- **Architect prompt bloat.** Asking for contracts in addition to components risks lower output quality. Mitigation: allow the Architect to skip contracts for components with no external interface (prompt must say so explicitly). Validate in tests.
- **Contract drift vs code.** Contracts are specs, not generated from code. Plancraft hands off before implementation, so this is acceptable; document it as a known limitation in the README.
- **Research privacy.** Clarification Q&A may contain sensitive user input. It was already in the DB; this milestone just writes it to disk. Ensure the workspace directory is user-scoped and excluded from any shared sync.

## Out of scope

- Contract linting (OpenAPI / JSON-Schema validation) → defer to M6's export evaluator, which can validate against the target format's schema.
- Bidirectional sync from a real codebase's OpenAPI file → separate feature.
- Version history on contracts → later.
