"""Write-side commands for feature entities."""
from __future__ import annotations

import re

from sqlalchemy import func, select

from models.db import Feature
from services.features.queries import FeatureQueries


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "feature"


class FeatureCommands:
    def __init__(self, db):
        self.db = db
        self.queries = FeatureQueries(db)

    async def create_feature(
        self,
        project_id: str,
        *,
        title: str,
        description: str = "",
        roadmap_item_id: str | None = None,
        status: str = "drafting",
    ) -> Feature:
        ordinal = await self._next_ordinal(project_id)
        slug = await self._next_unique_slug(project_id, title)
        feature = Feature(
            project_id=project_id,
            slug=slug,
            ordinal=ordinal,
            title=title.strip(),
            description=description.strip(),
            status=status,
            roadmap_item_id=roadmap_item_id,
        )
        self.db.add(feature)
        await self.db.commit()
        await self.db.refresh(feature)
        return feature

    async def update_feature(
        self,
        project_id: str,
        feature_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        roadmap_item_id: str | None = None,
    ) -> Feature:
        feature = await self.queries.get_feature(project_id, feature_id)
        if not feature:
            raise ValueError("Feature not found.")
        if title is not None and title.strip():
            feature.title = title.strip()
            feature.slug = await self._next_unique_slug(project_id, title, current_feature_id=feature.id)
        if description is not None:
            feature.description = description.strip()
        if status is not None:
            feature.status = status
        if roadmap_item_id is not None:
            feature.roadmap_item_id = roadmap_item_id or None
        await self.db.commit()
        await self.db.refresh(feature)
        return feature

    async def ensure_initial_feature(self, project_id: str) -> Feature:
        existing = await self.queries.list_features(project_id)
        if existing:
            return existing[0]
        return await self.create_feature(
            project_id,
            title="Initial",
            description="Synthetic initial feature that holds the project's legacy scoped artifacts.",
            status="done",
        )

    async def _next_ordinal(self, project_id: str) -> int:
        result = await self.db.execute(select(func.max(Feature.ordinal)).where(Feature.project_id == project_id))
        return (result.scalar_one() or 0) + 1

    async def _next_unique_slug(self, project_id: str, title: str, *, current_feature_id: str | None = None) -> str:
        base = _slugify(title)
        slug = base
        suffix = 2
        while True:
            stmt = select(Feature).where(Feature.project_id == project_id, Feature.slug == slug)
            if current_feature_id:
                stmt = stmt.where(Feature.id != current_feature_id)
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            if not existing:
                return slug
            slug = f"{base}-{suffix}"
            suffix += 1
