# Plancraft

> AI-powered software planning studio — from blank idea to a fully documented, implementation-ready project in five guided phases.

Plancraft walks you through a complete software planning workflow using specialised AI roles. Each phase unlocks progressively, building a structured knowledge base that culminates in an exportable task DAG and arc42 architecture documentation.

---

## What it does

You describe your idea. Plancraft's AI roles extract everything needed to build it:

```
🧭 Founder           →  mission, target users, product roadmap, tech-stack, constitution
        ↓
🔍 Business Analyst  →  problem statement, user stories, clarifications, constraints
        ↓
📋 Product Manager   →  epics, story priorities, MVP scope
        ↓
🏗️  Architect         →  components, architecture decisions (ADRs), interface contracts
        ↓
✅ TDD Tester        →  Given/When/Then test specs, implementation tasks
        ↓
🔎 Reviewer          →  deduplication, polish, cross-category consistency
        ↓
🏗  Scaffolder        →  implementation-ready code skeleton (impl/) — backend stubs, pytest files, optional Vite+React frontend
        ↓
📦 Export            →  workspace zip  +  task DAG JSON  +  arc42 Markdown  +  impl/ skeleton  +  spec-kit / Agent-OS / OpenSpec bundles
```

Each role executes inside an evaluator loop (ReAct): the actor produces an artifact, a rubric-driven evaluator scores it, and the loop retries up to `EVALUATOR_MAX_ITERATIONS` before escalating to the user with the critique shown. Traces are persisted per phase for inspection.

The exported task DAG is directly consumable by autonomous agent systems (e.g. [dev_team](https://github.com/mrstask/dev_team)) to kick off implementation without any manual handoff.

---

## Features

- **Evaluator-in-the-loop (ReAct)** — every role runs through `LoopController`: actor → evaluator (rubric-driven) → retry/escalate. When `EVALUATOR_ENABLED=false` every role uses `NullEvaluator` so traces are still written with no retries. Per-phase traces are persisted and browsable via `/traces`.
- **Constitution per project** — each project carries a `constitution.md` (seeded from a default template, inheritable from profiles) that the evaluator checks against. Rendered into the workspace under `.plancraft/constitution.md`.
- **Founder role + product triad** — a new Founder phase captures mission, target users, roadmap (with MVP flag), and tech-stack choices, rendered into `product/mission.md`, `product/roadmap.md`, and `product/tech-stack.md`.
- **Profiles (cross-project reusables)** — named profiles bundle constitution + tech-stack template + conventions. Projects can inherit from a profile at creation and save a profile from an existing project. Stored under `~/.plancraft/profiles` (path configurable via `PROFILES_ROOT`).
- **Multi-feature projects** — the Feature entity scopes stories, ADRs, test specs, tasks, clarifications, contracts, and research to a specific feature. Legacy single-feature projects are backfilled into a synthetic "initial" feature (behind `FEATURE_SCOPING_ENABLED`, defaults to `false`; dry-run and transactional).
- **Interface contracts + per-feature research** — architects capture API/event/schema contracts as `specs/NNN-slug/contracts/<kind>-<name>.md` and per-feature research/clarifications as `specs/NNN-slug/research.md`. Feature-local ADRs live in `specs/NNN-slug/adrs/`; cross-cutting ADRs remain in `architecture/adrs/`.
- **Pluggable exporter framework (M6)** — export targets are registered through a common `ExportTarget` contract with structural validators. Ships with `workspace`, `arc42`, `tasks`, `ba`, and `impl` targets; spec-kit / Agent-OS / OpenSpec targets can be added by implementing the contract (framework ready, bundled targets pending).
- **Scaffolder phase (M7)** — generates an implementation-ready code skeleton under `impl/`. Two-layer generation: a deterministic layer scaffolds the directory tree + static templates (bootstrap.sh, pyproject.toml, requirements.txt, conftest.py, optional Vite+React frontend); an LLM layer generates Python module stubs and pytest test files from components, contracts, tasks, and test specs. Method bodies are `raise NotImplementedError("TODO: TASK-NNN")` so tests fail by construction and a downstream dev team can fill them in.
- **Phase-gated flow** — each tab unlocks only when the previous phase produces real artifacts, keeping the conversation focused
- **Explicit MVP persistence** — the PM phase now saves the MVP cut and rationale, and architecture stays locked until both epics and MVP scope exist
- **Structured knowledge base** — every insight is persisted as a typed record (stories, epics, components, ADRs, test specs, tasks) with full SQLite backing
- **Local-first AI** — runs on Ollama (`gemma4:latest` for BA/PM/Architect, `gemma4:31b` for TDD/Review); no cloud API required
- **Centralized tool-calling discipline** — a shared LLM tool registry controls schemas, phase access, and dispatch in one place, with a fallback extraction pass when the model describes artifacts in prose
- **Deduplication** — exact-match upserts for components/epics/test specs; fuzzy `SequenceMatcher` deduplication for architecture decisions (threshold 0.50)
- **Multi-pass review** — the Reviewer runs 5 focused category passes then a holistic consistency check, each with atomic context so the model stays precise
- **Safer markdown rendering** — assistant/user markdown is rendered with `marked` and sanitized with DOMPurify before entering the DOM; if DOMPurify fails to load the renderer returns empty string rather than injecting raw HTML
- **Modular session UI** — the main planning screen now loads its controller from `static/js/session/` instead of embedding all interaction logic inside the template
- **Focused regression coverage** — unit tests cover phase gating, tool registration, MVP persistence, scoped artifact lookups, and story acceptance-criteria updates
- **Docs-as-code workspace** — each project gets its own directory (under `PROJECTS_ROOT`) with arc42 sections, individual ADR files, user-story files, test-spec files, task files, a Structurizr DSL C4 model, and a linked README; all files are regenerated from the DB after every LLM turn
- **Per-role context files** — `.plancraft/role-context/{role}.md` files are kept in sync so each LLM turn loads only the artifacts relevant to that role, staying within local-model context budgets
- **arc42 export** — full 12-section architecture documentation (split across files in-workspace, also downloadable as a single Markdown)
- **Task DAG export** — JSON with all tasks, dependencies, story links, and test spec links; ready for automated implementation pipelines
- **Workspace zip export** — download the complete docs-as-code directory as a zip; files are re-rendered fresh before packaging

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy (async) + aiosqlite |
| Frontend | Server-rendered Jinja + HTMX + Alpine.js + Tailwind CDN + small ES modules |
| AI | Ollama (OpenAI-compatible API) |
| Models | `gemma4:latest` / `gemma4:31b` |
| DB | SQLite |
| Testing | `unittest` |

No React, no build step — server-rendered HTML with HTMX partial swaps, Alpine.js for reactive state, and small browser modules for SSE/chat orchestration.

---

## Getting started

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running locally
- `gemma4:latest` and `gemma4:31b` pulled in Ollama

```bash
ollama pull gemma4:latest
ollama pull gemma4:31b
```

### Install & run

```bash
git clone git@github.com:mrstask/plancraft.git
cd plancraft

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # edit if needed

python main.py
# → http://localhost:8080
```

### Run tests

```bash
./.venv/bin/python -m unittest discover -s tests
```

### Environment (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=gemma4:latest
TDD_MODEL=gemma4:31b

# Root directory where per-project workspace folders are created
# Can be absolute or relative to the working directory
PROJECTS_ROOT=./projects

# Cross-project profile storage (constitutions, tech-stack templates, conventions)
PROFILES_ROOT=~/.plancraft/profiles

# Feature-scoping backfill (M4). Ship with `false`; flip to `true` only when
# ready to run the one-shot migration of legacy projects into an "initial" feature.
FEATURE_SCOPING_ENABLED=false

# Evaluator loop (M0). With EVALUATOR_ENABLED=false every role uses NullEvaluator:
# traces are written but no retries happen. Flip to `true` to enable real evaluation.
EVALUATOR_ENABLED=false
EVALUATOR_MAX_ITERATIONS=3
EVALUATOR_SCORE_THRESHOLD=0.8
EVALUATOR_ESCALATE_AFTER=2
EVALUATOR_MODEL=gemma4:latest
TRACE_RETENTION_DAYS=30
```

---

## Project structure

```
plancraft/
├── main.py                  # FastAPI entry point + lifespan (creates PROJECTS_ROOT on startup)
├── config.py                # Settings (Pydantic BaseSettings, includes PROJECTS_ROOT)
├── database.py              # SQLAlchemy engine + versioned startup migrations + workspace backfill
│
├── models/
│   ├── db.py                # ORM models (Project, UserStory, Component, MVP scope, …)
│   └── domain.py            # Pydantic command models + snapshot/phase status logic
│
├── roles/                   # AI role definitions (system prompt fragments)
│   ├── founder.py
│   ├── business_analyst.py
│   ├── ba_clarifications.py
│   ├── product_manager.py
│   ├── architect.py
│   ├── tdd_tester.py
│   ├── reviewer.py
│   └── scaffolder.py
│
├── services/
│   ├── knowledge/           # Knowledge-model read/write/context services
│   │   ├── commands.py      # Artifact creation, updates, deletes, MVP persistence
│   │   ├── queries.py       # Scoped artifact reads for UI and exports
│   │   ├── snapshots.py     # Knowledge snapshot builder for UI/LLM context
│   │   ├── contexts.py      # Phase-specific prompt context builders (file-first, DB fallback)
│   │   └── service.py       # Thin facade used by routers/orchestrators
│   ├── llm/                 # LLM orchestration package
│   │   ├── registry.py      # Shared tool registry + dispatcher
│   │   ├── prompts.py       # Phase-aware system prompt builder
│   │   ├── streaming.py     # Ollama streaming + extraction pass
│   │   ├── react_loop.py    # LoopController — actor → evaluator → retry/escalate
│   │   ├── trace_store.py   # Per-phase evaluator trace persistence
│   │   ├── evaluators/      # Evaluator implementations (NullEvaluator, rubric-scored)
│   │   └── rubrics/         # Role-specific evaluation rubrics
│   ├── features/            # Feature entity service (M4 — multi-feature projects)
│   ├── profiles/            # Profile service (M3 — cross-project reusables)
│   ├── scaffold/            # Scaffolder package (M7)
│   │   ├── tree_builder.py  # Deterministic directory tree + static templates
│   │   ├── llm.py           # LLM-driven module/test stub generator
│   │   ├── rubric.py        # Scaffolder evaluator rubric
│   │   └── tech_stack_reader.py  # Reads tech-stack to drive backend/frontend toggles
│   ├── export/
│   │   ├── queries.py       # Export-specific read models
│   │   ├── targets/         # Pluggable exporters: spec-kit, Agent-OS, OpenSpec
│   │   └── validators/      # Structural validators per export target
│   ├── workspace/           # Docs-as-code workspace package
│   │   ├── workspace.py     # ProjectWorkspace — path helpers + directory scaffold
│   │   ├── renderer.py      # Orchestrator: render_workspace() + schedule_render()
│   │   ├── role_context.py  # Per-role context file renderers with token budgets
│   │   ├── templates/       # Default constitution + other seed templates
│   │   └── renderers/
│   │       ├── arc42.py     # 12 individual arc42 section renderers
│   │       ├── adr.py       # Legacy (flat) ADR renderer
│   │       ├── adrs_split.py  # Splits feature-local vs cross-cutting ADRs (M5)
│   │       ├── constitution.py  # .plancraft/constitution.md (M1)
│   │       ├── mission.py / roadmap.py / tech_stack.py  # product/* (M2)
│   │       ├── feature_spec.py / feature_plan.py / feature_tasks.py  # specs/NNN/* (M4)
│   │       ├── contracts.py # specs/NNN/contracts/*.md (M5)
│   │       ├── research.py  # specs/NNN/research.md (M5)
│   │       ├── stories.py   # One US-NNN.md per user story
│   │       ├── specs.py     # One SPEC-NNN.md per test spec
│   │       ├── tasks.py     # TASK-NNN.md files + tasks.json DAG
│   │       ├── c4.py        # Structurizr DSL workspace.dsl
│   │       └── readme.py    # Root README.md with full ToC and cross-links
│   ├── review_orchestrator.py  # Multi-pass review pipeline
│   ├── export_service.py    # Task DAG + single-file arc42 builders (legacy)
│   └── suggestions.py       # Contextual follow-up suggestions
│
├── routers/
│   ├── projects.py          # Project CRUD + session view (workspace created on POST /projects)
│   ├── founder.py           # Founder-phase endpoints: mission, roadmap, tech-stack
│   ├── features.py          # Feature CRUD + feature-scoped session routes
│   ├── profiles.py          # Profile CRUD + inherit/save-from-project
│   ├── traces.py            # Evaluator trace inspection
│   ├── chat.py              # SSE chat + full review endpoint (triggers schedule_render per turn)
│   ├── docs.py              # Document tree sidebar
│   ├── scaffold.py          # POST /projects/{id}/scaffold (deterministic tree + LLM stubs)
│   └── export.py            # Download endpoints (workspace zip, task JSON, arc42 md, pluggable targets)
│
├── static/
│   ├── css/
│   │   └── app.css          # Small custom prose/layout styles
│   └── js/
│       └── session/         # Modular browser-side planning session logic
│
└── templates/
    ├── base.html             # Shared scripts/styles shell
    ├── session.html          # Main planning UI layout + bootstrap payload
    └── partials/             # HTMX partial templates

tests/
├── test_phase_status.py      # Phase gating rules
├── test_tool_registry.py     # Tool availability by phase
├── test_knowledge_service.py # MVP persistence + scoped reads + AC updates
├── test_workspace.py         # Workspace scaffold, renderers, and path helpers
├── test_scaffold_tree.py     # Deterministic scaffold tree + idempotency / force flag
└── test_scaffold_llm.py      # Scaffolder LLM tool dispatch + rubric scoring
```

---

## Architecture

Ownership is split across packages with clear boundaries:

- `services/knowledge/` owns the planning knowledge model itself.
- `services/llm/` owns prompt construction, streaming, tool registration, and fallback extraction.
- `services/workspace/` owns everything related to the per-project filesystem workspace — path resolution, directory scaffolding, all file renderers, and the background render orchestrator.
- `services/export/queries.py` owns read models tailored for export instead of reusing generic app queries.
- `static/js/session/` owns browser-side chat/review orchestration and keeps `templates/session.html` mostly declarative.

### Docs-as-code workspace

When a project is created, Plancraft scaffolds a directory under `PROJECTS_ROOT`:

```
{PROJECTS_ROOT}/{slug}-{short-id}/
├── README.md                      # index with links to all sections
├── docs/
│   ├── arc42/                     # 12 arc42 section files (interlinked)
│   ├── adr/                       # one NNNN-slug.md per architecture decision
│   ├── stories/                   # one US-NNN.md per user story
│   ├── c4/workspace.dsl           # Structurizr DSL (C4 context + container views)
│   └── diagrams/                  # generated diagram output (when Structurizr CLI present)
├── tests/specs/                   # one SPEC-NNN.md per test spec (Given/When/Then)
├── tasks/
│   ├── tasks.json                 # full task DAG for agent consumption
│   └── TASK-NNN.md                # one file per implementation task
└── .plancraft/
    └── role-context/              # pre-rendered per-role prompt context files
        ├── ba.md / pm.md / architect.md / tdd.md / review.md
```

**DB is the source of truth.** The filesystem is a materialized view re-rendered after each LLM turn as a background task (`schedule_render`). All writes are idempotent — re-rendering is always safe.

**Role context files** replace per-turn DB queries for the LLM system prompt. Each file is scoped to exactly what that role needs, keeping local-model context within budget. `PromptContextBuilder` reads the file if present and falls back to a DB query on the first turn (before the first render has run).

### C4 / Structurizr

The C4 renderer emits a `workspace.dsl` consumable by the [Structurizr CLI](https://github.com/structurizr/cli) to produce SVG/PNG diagrams. If the CLI is absent the DSL is still valid docs-as-code. The arc42 context and building-block sections link to the DSL file.

---

## Phase completion rules

- **Founder** completes when mission, ≥1 roadmap item, and ≥1 tech-stack entry exist, and the constitution has been acknowledged.
- **Business Analyst** completes when the project (or active feature) has a problem statement and at least one story. BA-clarifications may be run as an inner loop before handoff.
- **Product Manager** completes when the project has at least one epic and a saved MVP scope.
- **Architect** completes when the active feature has at least one component, one architecture decision, and the required contracts.
- **TDD Tester** completes when the active feature has at least one test spec and one implementation task.
- **Reviewer** completes once at least one final review trace exists (this also unlocks the Scaffolder).
- **Scaffolder** completes when `impl/.plancraft-scaffold.json` is present in the workspace.

### Phase 7: Scaffolder

**Trigger:** `POST /projects/{project_id}/scaffold`
**Unlock condition:** Reviewer phase must have run at least once (a final trace with `role="review"` exists). Pass `force=true` to bypass in development.

The Scaffolder generates an implementation-ready code skeleton inside the project workspace under `impl/`. A downstream dev team (or autonomous agent) then runs `bootstrap.sh` and fills in the method bodies.

Two-layer generation: a deterministic layer (no LLM) creates the directory tree + static template files (bootstrap.sh, pyproject.toml, requirements.txt, main.py, conftest.py; optional Vite+React frontend). An LLM layer generates Python stub modules and pytest test files from the project's components, contracts, tasks, and test specs. Every method body is `raise NotImplementedError("TODO: TASK-NNN")` so tests fail by construction.

Idempotency: if `impl/` exists with non-generated files (human edits), the endpoint returns HTTP 409 unless `force=true`.

Export: `GET /projects/{id}/export/download?target=impl` bundles the `impl/` tree.

---

## Exports

| Format | Endpoint | Description |
|--------|----------|-------------|
| Workspace zip | `GET /projects/{id}/export/workspace` | Zip of the full docs-as-code directory (re-rendered fresh) |
| Task DAG | `GET /projects/{id}/export/tasks` | JSON — tasks with dependencies, story & spec links |
| arc42 docs | `GET /projects/{id}/export/arc42` | Single Markdown — full 12-section architecture doc (legacy) |
| List targets | `GET /projects/{id}/export/targets` | List all registered pluggable exporters (M6) |
| Target bundle | `GET /projects/{id}/export/download?target=<name>` | Build + validate + zip any registered target (`workspace`, `arc42`, `tasks`, `ba`, `impl`) |
| Scaffold trigger | `POST /projects/{id}/scaffold` | Generate the `impl/` code skeleton (Reviewer must have run; pass `force=true` to override) |

---

## How the multi-pass review works

The **🔎 Full review** button runs a 6-pass pipeline — not a single LLM call:

1. **Stories pass** — reviews only stories, with only stories as context
2. **Components pass** — reviews only components
3. **Decisions pass** — reviews only ADRs (fuzzy duplicate detection)
4. **Test specs pass** — reviews specs, fills in empty Given/When/Then
5. **Tasks pass** — reviews tasks, improves missing descriptions
6. **Holistic pass** — re-reads the full (now cleaned) knowledge base for cross-category consistency

Each pass is atomic — the model stays focused, avoids context dilution, and the next pass always starts from already-cleaned data.

---

## Development notes

- Startup migrations are version-tracked in a `schema_migrations` table and run after `create_all()`.
- All artifact reads **and writes** are project-scoped — the `project_id` is validated in every mutation's WHERE clause, so an artifact from Project A cannot be modified by a session in Project B even if the UUID is known.
- SQLite foreign-key enforcement is enabled on every connection (`PRAGMA foreign_keys=ON`) and junction tables use `ON DELETE CASCADE`, so deleting a story or test spec automatically cleans up orphaned task-link rows.
- Chat history sent to the model is capped at `MAX_HISTORY_MESSAGES` (default 50) to prevent context-window overflow as sessions grow.
- The PM and TDD contexts include full artifact IDs when the model needs to make linking or scope-setting tool calls.
- Role context files (`.plancraft/role-context/`) are written by `schedule_render()` after each turn and read back on the next turn by `PromptContextBuilder`, making per-role context deterministic and diffable.
- Workspace rendering is fire-and-forget (`asyncio.ensure_future`) — a render failure never breaks the chat response.
- On first startup, `_backfill_workspaces()` creates workspace directories for any existing projects that predate this feature.

---

## License

MIT
