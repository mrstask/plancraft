# M3 — Profile entity

**Duration:** 3 days
**Depends on:** M1 (profile seeds constitution), M2 (profile seeds tech-stack templates)
**Blocks:** — (independent of M4+)
**Status:** not started

## Goal

Profiles are cross-project reusable bundles of constitution + tech-stack defaults + convention snippets. A new project can inherit from a profile at creation time, after which it diverges independently. A project can be saved back as a new profile.

## Why this milestone

Plancraft is currently fully per-project. Users building similar projects (e.g., several Django SaaS tools, several CLI utilities) re-enter the same rules every time. Profiles close that gap while keeping the single-source-of-truth principle: a profile seeds the project and then steps away.

## Data model

### New table + storage

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    constitution_md TEXT NOT NULL,
    tech_stack_template TEXT NOT NULL,          -- YAML: list of {layer, choice, rationale}
    conventions_json TEXT NOT NULL DEFAULT '{}', -- free-form key/value blobs
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Profiles live in a separate on-disk root (`PROFILES_ROOT` env, default `~/.plancraft/profiles/`). On-disk layout mirrors the table: one directory per profile with `constitution.md`, `tech-stack.yml`, `conventions.json`, `profile.yml`. The DB is the source of truth; disk is the human-editable mirror.

### Use of existing `projects.profile_ref` (added in M1)

Populated on inherit to `{profile_name}@{version}`. Purely informational — no live link, no cascading edits.

## Code changes

### Files created
- `services/profiles/` — new package:
  - `commands.py` (create, update, delete, `save_from_project`).
  - `queries.py` (list, get by name).
  - `renderer.py` (keep disk mirror in sync).
- `routers/profiles.py` — CRUD endpoints + UI routes.
- `templates/profiles/` — list / detail / edit views.
- `services/workspace/templates/starter_profiles/` — a couple of ship-with-the-app profiles (`generic.yml`, `python-web-app.yml`, `cli-tool.yml`). Loaded on first run if no profiles exist.

### Files modified
- `models/db.py`, `models/domain.py` — new `Profile` record.
- `config.py` — `PROFILES_ROOT` env var (default `~/.plancraft/profiles/`).
- Project-create flow (wherever that lives — likely `routers/` project bootstrap): add `profile_id` optional selector. On select, copy constitution + tech-stack into the new project; set `projects.profile_ref`.
- Main navbar: new "Profiles" top-level page, outside any project.

## `save_from_project` extraction

Command signature: `save_profile_from_project(project_id, profile_name, *, description, strip_project_refs: bool = True) -> Profile`.

Behavior:
1. Read `Project.constitution_md`, `tech_stack_entries`, selected cross-cutting ADRs.
2. If `strip_project_refs`, run a lightweight LLM pass (or regex heuristic) to remove sentences mentioning the project by name.
3. Write to the new `Profile` row + disk mirror.
4. Return the profile for display.

## UI

- **Profiles list page** (`/profiles`): cards showing name, description, version, updated date. Actions: edit, delete, duplicate.
- **Profile edit view**: three panels — constitution (markdown), tech-stack (table), conventions (key-value editor).
- **New project flow**: radio toggle — "Start blank" vs "Inherit from profile …". On inherit, preview the constitution before confirming.
- **Inside project**: small badge near project title showing `from profile:rails-saas@1.2.0` if inherited. Click → opens the source profile (read-only tooltip saying divergence is expected).
- **Save-as-profile button** inside project settings.

## Tests

- `tests/test_profiles.py`
  - CRUD round-trip, DB + disk mirror.
  - Starter profiles loaded on first run.
  - Duplicate-name rejected.
- `tests/test_project_inherit.py`
  - Create project from profile → project constitution equals profile's at creation.
  - Edit project constitution → profile unchanged.
  - Edit profile constitution → existing projects unchanged.
- `tests/test_save_from_project.py`
  - `strip_project_refs=True` removes project-specific sentences.
  - Resulting profile is valid input to another inherit.

## Migration

- Create `profiles` table.
- On first run: if `profiles` is empty and `PROFILES_ROOT` is empty, seed starter profiles.

## Exit criteria

- [ ] Create profile → create project from it → diverge independently.
- [ ] Save-from-project produces a profile that successfully seeds a new project.
- [ ] Starter profiles load on fresh install.
- [ ] Profile disk mirror stays in sync with DB on every edit.
- [ ] Deleting a profile does not affect projects that inherited from it.

## Risks

- **Two sources of truth (DB + disk).** Users will hand-edit the disk files. Decide early: DB-wins-on-conflict (simpler) vs disk-wins (lets users edit outside the app). **Recommendation: DB-wins, with a "reload from disk" action.**
- **Strip-project-refs heuristic.** Removing project-specific sentences is lossy. Offer a diff preview before saving.
- **Starter profile drift.** If we ship starter profiles and then update them in the app, existing users don't get updates. Decision: starter profiles seed once and never auto-update; users copy-diff manually if they want updates. Document this.

## Out of scope

- Profile versioning with upgrade paths → deferred; bump `version` manually for now.
- Sharing profiles across machines → deferred; users can copy `PROFILES_ROOT` directories.
- Profile marketplaces / import from URL → deferred.
