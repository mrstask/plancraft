from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
