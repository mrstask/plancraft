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
    """Add columns introduced after initial schema — idempotent (ignores errors if column exists)."""
    new_columns = [
        "ALTER TABLE messages  ADD COLUMN role_tab      VARCHAR DEFAULT 'ba'",
        "ALTER TABLE projects  ADD COLUMN current_phase VARCHAR DEFAULT 'ba'",
    ]
    async with engine.begin() as conn:
        for sql in new_columns:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # column already exists — SQLite has no IF NOT EXISTS for ALTER TABLE
