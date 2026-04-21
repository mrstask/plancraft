"""Read-side helpers for reusable profiles."""
from __future__ import annotations

from sqlalchemy import select

from models.db import Profile


def split_profile_ref(profile_ref: str) -> tuple[str, str | None]:
    if "@" not in profile_ref:
        return profile_ref.strip(), None
    name, version = profile_ref.rsplit("@", 1)
    return name.strip(), version.strip() or None


class ProfileQueries:
    def __init__(self, db):
        self.db = db

    async def list_profiles(self) -> list[Profile]:
        result = await self.db.execute(select(Profile).order_by(Profile.updated_at.desc(), Profile.name.asc()))
        return list(result.scalars().all())

    async def get_profile(self, profile_id: str) -> Profile | None:
        result = await self.db.execute(select(Profile).where(Profile.id == profile_id))
        return result.scalar_one_or_none()

    async def get_profile_by_name(self, name: str) -> Profile | None:
        result = await self.db.execute(select(Profile).where(Profile.name == name))
        return result.scalar_one_or_none()

    async def get_profile_by_ref(self, profile_ref: str) -> Profile | None:
        name, version = split_profile_ref(profile_ref)
        stmt = select(Profile).where(Profile.name == name)
        if version:
            stmt = stmt.where(Profile.version == version)
        stmt = stmt.order_by(Profile.updated_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

