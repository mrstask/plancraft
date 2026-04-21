"""Read-side queries for feature entities."""
from __future__ import annotations

from sqlalchemy import select

from models.db import Feature


class FeatureQueries:
    def __init__(self, db):
        self.db = db

    async def list_features(self, project_id: str) -> list[Feature]:
        result = await self.db.execute(
            select(Feature).where(Feature.project_id == project_id).order_by(Feature.ordinal.asc(), Feature.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_feature(self, project_id: str, feature_id: str) -> Feature | None:
        result = await self.db.execute(
            select(Feature).where(Feature.project_id == project_id, Feature.id == feature_id)
        )
        return result.scalar_one_or_none()
