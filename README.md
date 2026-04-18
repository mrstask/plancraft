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
📦 Export            →  task DAG JSON  +  arc42 Markdown
```

The exported task DAG is directly consumable by autonomous agent systems (e.g. [dev_team](https://github.com/mrstask/dev_team)) to kick off implementation without any manual handoff.

---

## Features

- **Phase-gated flow** — each tab unlocks only when the previous phase produces real artifacts, keeping the conversation focused
- **Structured knowledge base** — every insight is persisted as a typed record (stories, epics, components, ADRs, test specs, tasks) with full SQLite backing
- **Local-first AI** — runs on Ollama (`gemma4:latest` for BA/PM/Architect, `gemma4:31b` for TDD/Review); no cloud API required
- **Tool-calling discipline** — phase-scoped tool subsets, `tool_choice=required` for critical phases, and a fallback extraction pass ensure the model always saves structured data
- **Deduplication** — exact-match upserts for components/epics/test specs; fuzzy `SequenceMatcher` deduplication for architecture decisions (threshold 0.50)
- **Multi-pass review** — the Reviewer runs 5 focused category passes then a holistic consistency check, each with atomic context so the model stays precise
- **arc42 export** — full 12-section architecture documentation generated from the knowledge base
- **Task DAG export** — JSON with all tasks, dependencies, story links, and test spec links; ready for automated implementation pipelines

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy (async) + aiosqlite |
| Frontend | HTMX + Alpine.js + Tailwind CSS |
| AI | Ollama (OpenAI-compatible API) |
| Models | `gemma4:latest` / `gemma4:31b` |
| DB | SQLite |

No React, no build step — server-rendered HTML with HTMX partial swaps and Alpine.js for reactive state.

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

### Environment (`.env`)

```env
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=gemma4:latest
TDD_MODEL=gemma4:31b
```

---

## Project structure

```
plancraft/
├── main.py                  # FastAPI entry point + lifespan
├── config.py                # Settings (Pydantic BaseSettings)
├── database.py              # SQLAlchemy engine + migrations
│
├── models/
│   ├── db.py                # ORM models (Project, UserStory, Component, …)
│   └── domain.py            # Pydantic domain models + phase status logic
│
├── roles/                   # AI role definitions (system prompt fragments)
│   ├── business_analyst.py
│   ├── product_manager.py
│   ├── architect.py
│   ├── tdd_tester.py
│   └── reviewer.py
│
├── services/
│   ├── knowledge.py         # CRUD over the knowledge base
│   ├── llm.py               # Ollama streaming, tool dispatch, phase routing
│   ├── review_orchestrator.py  # Multi-pass review pipeline
│   ├── export_service.py    # Task DAG + arc42 builders
│   └── suggestions.py       # Contextual follow-up suggestions
│
├── routers/
│   ├── projects.py          # Project CRUD + session view
│   ├── chat.py              # SSE chat + full review endpoint
│   ├── docs.py              # Document tree sidebar
│   └── export.py            # Download endpoints
│
└── templates/
    ├── base.html
    ├── session.html          # Main planning UI
    └── partials/             # HTMX partial templates
```

---

## Exports

| Format | Endpoint | Description |
|--------|----------|-------------|
| Task DAG | `GET /projects/{id}/export/tasks` | JSON — tasks with dependencies, story & spec links |
| arc42 docs | `GET /projects/{id}/export/arc42` | Markdown — full 12-section architecture doc |

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

## License

MIT
