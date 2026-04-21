from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable FK enforcement for every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        from models import db  # noqa: F401 — registers all ORM models
        await conn.run_sync(Base.metadata.create_all)


async def _backfill_workspaces() -> None:
    """Create workspace directories for existing projects that don't have one."""
    from sqlalchemy import select as _select
    from models.db import Project as _Project

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            _select(_Project).where(_Project.root_path.is_(None))
        )
        projects = result.scalars().all()
        if not projects:
            return

        from services.workspace.workspace import ProjectWorkspace
        for project in projects:
            ws = ProjectWorkspace.create(project.name, project.id)
            project.root_path = str(ws.root)

        await db.commit()

        import logging
        logging.getLogger(__name__).info(
            "Backfilled workspace paths for %d existing project(s)", len(projects)
        )


async def _backfill_constitutions() -> None:
    """Seed the default constitution for projects that have none."""
    from pathlib import Path as _Path
    from sqlalchemy import select as _select
    from models.db import Project as _Project

    template_path = _Path(__file__).parent / "services/workspace/templates/default_constitution.md"
    if not template_path.exists():
        return
    default_md = template_path.read_text(encoding="utf-8")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            _select(_Project).where(
                (_Project.constitution_md == None) | (_Project.constitution_md == "")  # noqa: E711
            )
        )
        projects = result.scalars().all()
        if not projects:
            return
        for project in projects:
            project.constitution_md = default_md
        await db.commit()

        import logging
        logging.getLogger(__name__).info(
            "Backfilled default constitution for %d project(s)", len(projects)
        )


async def _backfill_feature_scoping(*, dry_run: bool = False) -> list[dict]:
    """Create synthetic initial features for legacy projects and scope legacy artifacts to them."""
    from sqlalchemy import select as _select
    from models.db import ArchitectureDecision as _Decision
    from models.db import Feature as _Feature
    from models.db import Message as _Message
    from models.db import Project as _Project
    from models.db import Task as _Task
    from models.db import TestSpec as _TestSpec
    from models.db import UserStory as _UserStory

    summaries: list[dict] = []
    async with AsyncSessionLocal() as db:
        projects = (
            await db.execute(_select(_Project).order_by(_Project.created_at.asc()))
        ).scalars().all()

        for project in projects:
            existing_feature = (
                await db.execute(
                    _select(_Feature).where(_Feature.project_id == project.id).order_by(_Feature.ordinal.asc())
                )
            ).scalars().first()

            if not existing_feature:
                feature = _Feature(
                    project_id=project.id,
                    slug="initial",
                    ordinal=1,
                    title="Initial",
                    description="Synthetic feature created during M4 backfill to hold pre-feature scoped artifacts.",
                    status="done",
                )
                db.add(feature)
                await db.flush()
            else:
                feature = existing_feature

            story_rows = (
                await db.execute(
                    _select(_UserStory).where(_UserStory.project_id == project.id, _UserStory.feature_id.is_(None))
                )
            ).scalars().all()
            spec_rows = (
                await db.execute(
                    _select(_TestSpec).where(_TestSpec.project_id == project.id, _TestSpec.feature_id.is_(None))
                )
            ).scalars().all()
            task_rows = (
                await db.execute(
                    _select(_Task).where(_Task.project_id == project.id, _Task.feature_id.is_(None))
                )
            ).scalars().all()
            message_rows = (
                await db.execute(
                    _select(_Message).where(_Message.project_id == project.id, _Message.feature_id.is_(None))
                )
            ).scalars().all()
            decision_rows = (
                await db.execute(
                    _select(_Decision).where(_Decision.project_id == project.id, _Decision.feature_id.is_(None))
                )
            ).scalars().all()

            summaries.append(
                {
                    "project_id": project.id,
                    "feature_id": feature.id,
                    "stories": len(story_rows),
                    "test_specs": len(spec_rows),
                    "tasks": len(task_rows),
                    "messages": len(message_rows),
                    "decisions_left_cross_cutting": len(decision_rows),
                }
            )

            if dry_run:
                await db.rollback()
                continue

            for row in story_rows:
                row.feature_id = feature.id
            for row in spec_rows:
                row.feature_id = feature.id
            for row in task_rows:
                row.feature_id = feature.id
            for row in message_rows:
                if (row.role_tab or "") in {"ba", "architect", "tdd", "review"}:
                    row.feature_id = feature.id

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    return summaries


async def migrate_db():
    """Run versioned schema migrations after the base metadata exists."""
    migrations: list[tuple[str, list[str]]] = [
        (
            "20260418_add_phase_tracking",
            [
                "ALTER TABLE messages ADD COLUMN role_tab VARCHAR DEFAULT 'ba'",
                "ALTER TABLE projects ADD COLUMN current_phase VARCHAR DEFAULT 'ba'",
            ],
        ),
        (
            "20260418_add_mvp_scope",
            [
                "ALTER TABLE projects ADD COLUMN mvp_story_ids JSON",
                "ALTER TABLE projects ADD COLUMN mvp_rationale TEXT",
            ],
        ),
        (
            "20260421_add_constitution",
            [
                "ALTER TABLE projects ADD COLUMN constitution_md TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE projects ADD COLUMN profile_ref VARCHAR(128)",
            ],
        ),
        (
            "20260421_add_founder_artifacts",
            [
                "CREATE TABLE IF NOT EXISTS project_missions ("
                "id VARCHAR PRIMARY KEY, "
                "project_id VARCHAR NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE, "
                "statement TEXT NOT NULL DEFAULT '', "
                "target_users TEXT NOT NULL DEFAULT '', "
                "problem TEXT NOT NULL DEFAULT '', "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
                "CREATE TABLE IF NOT EXISTS project_roadmap_items ("
                "id VARCHAR PRIMARY KEY, "
                "project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                "ordinal INTEGER NOT NULL, "
                "title VARCHAR(256) NOT NULL DEFAULT '', "
                "description TEXT NOT NULL DEFAULT '', "
                "linked_epic_id VARCHAR NULL REFERENCES epics(id) ON DELETE SET NULL, "
                "mvp BOOLEAN NOT NULL DEFAULT 0, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
                "CREATE TABLE IF NOT EXISTS tech_stack_entries ("
                "id VARCHAR PRIMARY KEY, "
                "project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                "layer VARCHAR(64) NOT NULL DEFAULT '', "
                "choice VARCHAR(256) NOT NULL DEFAULT '', "
                "rationale TEXT NOT NULL DEFAULT '', "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
            ],
        ),
        (
            "20260421_add_profiles",
            [
                "CREATE TABLE IF NOT EXISTS profiles ("
                "id VARCHAR PRIMARY KEY, "
                "name VARCHAR(128) NOT NULL UNIQUE, "
                "description TEXT NOT NULL DEFAULT '', "
                "version VARCHAR(32) NOT NULL DEFAULT '1.0.0', "
                "constitution_md TEXT NOT NULL DEFAULT '', "
                "tech_stack_template TEXT NOT NULL DEFAULT '[]', "
                "conventions_json TEXT NOT NULL DEFAULT '{}', "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
            ],
        ),
        (
            "20260421_add_feature_scoping",
            [
                "CREATE TABLE IF NOT EXISTS features ("
                "id VARCHAR PRIMARY KEY, "
                "project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                "slug VARCHAR(128) NOT NULL, "
                "ordinal INTEGER NOT NULL, "
                "title VARCHAR(256) NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', "
                "status VARCHAR(32) NOT NULL DEFAULT 'drafting', "
                "roadmap_item_id VARCHAR NULL REFERENCES project_roadmap_items(id) ON DELETE SET NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_features_project_ordinal ON features(project_id, ordinal)",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_features_project_slug ON features(project_id, slug)",
                "ALTER TABLE messages ADD COLUMN feature_id VARCHAR",
                "ALTER TABLE user_stories ADD COLUMN feature_id VARCHAR",
                "ALTER TABLE architecture_decisions ADD COLUMN feature_id VARCHAR",
                "ALTER TABLE test_specs ADD COLUMN feature_id VARCHAR",
                "ALTER TABLE tasks ADD COLUMN feature_id VARCHAR",
            ],
        ),
        (
            "20260421_add_contracts_and_feature_research",
            [
                "ALTER TABLE clarification_points ADD COLUMN feature_id VARCHAR",
                "CREATE TABLE IF NOT EXISTS interface_contracts ("
                "id VARCHAR PRIMARY KEY, "
                "project_id VARCHAR NOT NULL REFERENCES projects(id) ON DELETE CASCADE, "
                "feature_id VARCHAR NULL REFERENCES features(id) ON DELETE CASCADE, "
                "component_id VARCHAR NOT NULL REFERENCES components(id) ON DELETE CASCADE, "
                "kind VARCHAR(32) NOT NULL, "
                "name VARCHAR(256) NOT NULL, "
                "body_md TEXT NOT NULL DEFAULT '', "
                "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                ")",
                "CREATE INDEX IF NOT EXISTS idx_contracts_feature ON interface_contracts(feature_id)",
            ],
        ),
        (
            "20260421_add_ba_structured_fields",
            [
                "ALTER TABLE projects ADD COLUMN business_goals JSON",
                "ALTER TABLE projects ADD COLUMN success_metrics JSON",
                "ALTER TABLE projects ADD COLUMN in_scope JSON",
                "ALTER TABLE projects ADD COLUMN out_of_scope JSON",
                "ALTER TABLE projects ADD COLUMN target_users JSON",
                "ALTER TABLE projects ADD COLUMN terminology JSON",
                "ALTER TABLE projects ADD COLUMN llm_interaction_model JSON",
                "ALTER TABLE messages ADD COLUMN active_persona VARCHAR",
            ],
        ),
    ]

    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version VARCHAR PRIMARY KEY, "
            "applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ))

        applied_rows = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in applied_rows}

        for version, statements in migrations:
            if version in applied:
                continue
            for sql in statements:
                try:
                    await conn.execute(text(sql))
                except Exception as exc:
                    # Fresh databases already have the latest schema because create_all()
                    # runs before migrations, so duplicate-column failures are expected.
                    if "duplicate column name" not in str(exc).lower():
                        raise
            await conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": version},
            )

    # Backfill workspace directories for existing projects
    await _backfill_workspaces()
    # Backfill empty constitutions with the default template
    await _backfill_constitutions()
    # Backfill legacy artifacts into an initial feature when feature scoping is enabled
    if settings.feature_scoping_enabled:
        await _backfill_feature_scoping(dry_run=False)
