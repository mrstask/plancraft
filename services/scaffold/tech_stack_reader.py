"""Read DB tech-stack entries and produce a ScaffoldConfig."""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import TechStackEntry

# Keywords that signal a frontend layer exists in the tech stack
_FRONTEND_RE = re.compile(
    r"\b(react|vue|angular|svelte|next\.?js|vite|nuxt|remix|frontend|ui|spa|web\s*app|browser)\b",
    re.IGNORECASE,
)


@dataclass
class ScaffoldConfig:
    has_frontend: bool
    backend: str = "python"        # always python for now
    frontend: str | None = None    # "node" when has_frontend else None
    package_slug: str = "app"      # Python package name derived from project name slug


async def read_scaffold_config(
    project_id: str,
    db: AsyncSession,
    package_slug: str = "app",
) -> ScaffoldConfig:
    """Read tech-stack entries and determine whether a frontend should be scaffolded.

    Decision rule: if ANY tech-stack entry's layer OR choice contains a known
    frontend keyword the frontend tree is included.  Otherwise it is skipped.
    """
    result = await db.execute(
        select(TechStackEntry).where(TechStackEntry.project_id == project_id)
    )
    entries = result.scalars().all()

    has_frontend = any(
        _FRONTEND_RE.search(f"{e.layer} {e.choice}") for e in entries
    )

    return ScaffoldConfig(
        has_frontend=has_frontend,
        backend="python",
        frontend="node" if has_frontend else None,
        package_slug=package_slug,
    )
