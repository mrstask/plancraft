# Plancraft

> AI-powered software planning studio — from blank idea to a fully documented, implementation-ready project in five guided phases.

Plancraft walks you through a complete software planning workflow using specialised AI roles. Each phase unlocks progressively, building a structured knowledge base that culminates in an exportable task DAG and arc42 architecture documentation.

---

## What it does

You describe your idea. Plancraft's AI roles extract everything needed to build it:

```
🔍 Business Analyst  →  problem statement, user stories, constraints
        ↓
📋 Product Manager   →  epics, story priorities, MVP scope
        ↓
🏗️  Architect         →  components, architecture decisions (ADRs)
        ↓
✅ TDD Tester        →  Given/When/Then test specs, implementation tasks
        ↓
🔎 Reviewer          →  deduplication, polish, cross-category consistency
        ↓
📦 Export            →  workspace zip  +  task DAG JSON  +  arc42 Markdown
```

The exported task DAG is directly consumable by autonomous agent systems (e.g. [dev_team](https://github.com/mrstask/dev_team)) to kick off implementation without any manual handoff.

---

## Features

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
│   ├── business_analyst.py
│   ├── product_manager.py
│   ├── architect.py
│   ├── tdd_tester.py
│   └── reviewer.py
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
│   │   └── streaming.py     # Ollama streaming + extraction pass
│   ├── export/
│   │   └── queries.py       # Export-specific read models
│   ├── workspace/           # Docs-as-code workspace package
│   │   ├── workspace.py     # ProjectWorkspace — path helpers + directory scaffold
│   │   ├── renderer.py      # Orchestrator: render_workspace() + schedule_render()
│   │   ├── role_context.py  # Per-role context file renderers with token budgets
│   │   └── renderers/
│   │       ├── arc42.py     # 12 individual arc42 section renderers
│   │       ├── adr.py       # One NNNN-slug.md per architecture decision
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
│   ├── chat.py              # SSE chat + full review endpoint (triggers schedule_render per turn)
│   ├── docs.py              # Document tree sidebar
│   └── export.py            # Download endpoints (workspace zip, task JSON, arc42 md)
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
└── test_workspace.py         # Workspace scaffold, renderers, and path helpers
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

- **Business Analyst** completes when the project has a problem statement and at least one story.
- **Product Manager** completes when the project has at least one epic and a saved MVP scope.
- **Architect** completes when the project has at least one component and one architecture decision.
- **TDD Tester** completes when the project has at least one test spec and one implementation task.
- **Reviewer** remains an optional cleanup phase before export.

---

## Exports

| Format | Endpoint | Description |
|--------|----------|-------------|
| Workspace zip | `GET /projects/{id}/export/workspace` | Zip of the full docs-as-code directory (re-rendered fresh) |
| Task DAG | `GET /projects/{id}/export/tasks` | JSON — tasks with dependencies, story & spec links |
| arc42 docs | `GET /projects/{id}/export/arc42` | Single Markdown — full 12-section architecture doc (legacy) |

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
