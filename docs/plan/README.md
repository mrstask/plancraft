# Plancraft-vNext Implementation Plan

Consolidated plan for evolving Plancraft into a multi-feature, constitution-driven planning studio that exports to spec-kit / Agent OS / OpenSpec formats, with an evaluator-in-the-loop at every role step.

This directory is the source of truth for the plan. Each milestone has its own detailed design file.

---

## Guiding principles

- **Evaluator-ready from day 1.** Every role-execution path routes through `LoopController` even if no evaluator is wired yet. Retrofitting the loop later is painful; adding a no-op loop now is cheap.
- **Ship increments that are useful alone.** Each milestone ends with a working app, not a half-migrated one.
- **Smaller project-level wins first, feature-loop last.** M1–M3 don't need the Feature entity, so we exercise the evaluator loop on simple surfaces before the biggest structural change.
- **Local-first discipline preserved.** All changes must keep the app runnable on local Ollama without cloud dependencies.

---

## Target workspace layout

```
<project>/
├── .plancraft/
│   ├── constitution.md           # governing principles (from profile, then edited)
│   ├── profile.yml               # which profile was inherited + version
│   └── role-context/             # per-role LLM context (already exists)
├── product/
│   ├── mission.md                # why
│   ├── roadmap.md                # epics + MVP + ordering
│   └── tech-stack.md             # chosen components / technologies
├── specs/                        # feature-scoped, numbered, iterative
│   ├── 001-user-onboarding/
│   │   ├── spec.md              # BA: stories + acceptance
│   │   ├── research.md          # BA-clarifications Q&A
│   │   ├── plan.md              # Architect: component-level changes
│   │   ├── data-model.md
│   │   ├── contracts/           # API / interface shapes
│   │   ├── tasks.md             # task DAG
│   │   └── adrs/                # feature-local ADRs
│   └── 002-payment-integration/
├── architecture/                 # cross-feature, long-lived
│   ├── arc42/                    # (already exists)
│   ├── adrs/                     # cross-cutting ADRs
│   └── c4.dsl                    # (already exists)
└── README.md                     # generated index
```

Three scopes with clear boundaries: **profile** (cross-project) · **project** (product + architecture + constitution) · **feature** (`specs/NNN/`).

---

## Milestones

| # | Milestone | Days | Blocks | File |
|---|---|---|---|---|
| M0 | Evaluator loop scaffolding | 2–3 | all others | [M0-evaluator-loop.md](M0-evaluator-loop.md) |
| M1 | Constitution + first real evaluator | 2 | M3 | [M1-constitution.md](M1-constitution.md) |
| M2 | Founder role + product triad | 2–3 | — | [M2-founder-role.md](M2-founder-role.md) |
| M3 | Profile entity | 3 | — | [M3-profile-entity.md](M3-profile-entity.md) |
| M4 | Feature entity + feature loop | 5–7 | M5, M6 | [M4-feature-loop.md](M4-feature-loop.md) |
| M5 | contracts/, research.md, per-feature ADRs | 2 | M6 | [M5-contracts-research.md](M5-contracts-research.md) |
| M6 | Pluggable exporters (spec-kit / agent-os / openspec) | 3 | — | [M6-pluggable-exporters.md](M6-pluggable-exporters.md) |

**~3 weeks total** sequentially for one person. M2 and M3 can parallelize with M1 after M0 lands.

---

## Cross-cutting decisions to lock before starting

1. **Feature-loop confirmation.** M4 is a week of work and reshapes the data model. If users will not come back to projects to spec feature 002, cut M4 and stop at M3.
2. **Evaluator model choice.** Same model class as the actor, with a narrower context (rubric + actor output, not full project context). Local-cheap evaluator is fine for rubric lint but weak for nuanced constitution checks.
3. **Evaluator failure policy on max-iterations exceeded without convergence.** Options: (a) auto-accept with warning, (b) escalate to user with critique shown, (c) hard-fail and block the phase. **Default: (b).** User stays in control without losing work.
4. **Trace retention.** Keep all iterations for the current phase; collapse older phases to "final only" after N days. Configurable via env.

---

## Global risks

- **Backfill migration in M4** is the highest-risk step. Write defensively: dry-run mode, transactional, reversible.
- **Context budget in feature loop.** Per-feature + constitution + cross-cutting ADRs may exceed local-model budgets. The per-role context files in `services/workspace/role_context.py` make this solvable — formalize a "summary vs. full" toggle per artifact.
- **Evaluator thrash.** An over-strict evaluator causes retries to the cap. Always cap at `max_iterations` and trust the escalation path.

---

## How the evaluator loop shows in the UI

```
BA · feature 002 "payment integration" · 2/3 iterations ⚠︎
  ├─ 1  score 0.62 · missing acceptance criteria on S-7
  ├─ 2  score 0.84 ✓ accepted
  └─ artifacts: 4 stories, 2 constraints
```

Clickable to expand each iteration's prompt / output / critique.

---

## What to read next

- **Start here:** [M0-evaluator-loop.md](M0-evaluator-loop.md) — the foundation every later milestone builds on.
- If you only have time for one real-evaluator win: read [M1-constitution.md](M1-constitution.md).
- If you want the iteration model (multi-feature projects): read [M4-feature-loop.md](M4-feature-loop.md).
