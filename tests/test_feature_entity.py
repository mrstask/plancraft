from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Project
from services.features import FeatureCommands, FeatureQueries


class FeatureEntityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_feature_crud_assigns_ordinals_and_unique_slugs(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            commands = FeatureCommands(session)
            first = await commands.create_feature(project.id, title="User Onboarding", description="First flow")
            second = await commands.create_feature(project.id, title="User Onboarding", description="Second flow")

            self.assertEqual(first.ordinal, 1)
            self.assertEqual(first.slug, "user-onboarding")
            self.assertEqual(second.ordinal, 2)
            self.assertEqual(second.slug, "user-onboarding-2")

            updated = await commands.update_feature(project.id, second.id, status="ready", title="Payments")
            self.assertEqual(updated.slug, "payments")
            self.assertEqual(updated.status, "ready")

            listed = await FeatureQueries(session).list_features(project.id)
            self.assertEqual([item.ordinal for item in listed], [1, 2])


if __name__ == "__main__":
    unittest.main()
