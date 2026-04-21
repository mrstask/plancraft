"""Shared helpers for knowledge-model services."""
from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import Project


def similarity(a: str, b: str) -> float:
    """Return a 0-1 similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def decision_fingerprint(title: str, decision: str) -> str:
    """Combine title + decision text for a richer similarity signal."""
    return f"{title} {decision}"


class KnowledgeBase:
    def __init__(self, db: AsyncSession, feature_id: str | None = None):
        self.db = db
        self.feature_id = feature_id

    async def get_project(self, project_id: str) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        return project
