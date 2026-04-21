from __future__ import annotations

import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import database as database_module
from database import Base, _backfill_feature_scoping
from models import db as models_db  # noqa: F401
from models.db import ArchitectureDecision, Message, Project, Task, TestSpec, UserStory


class BackfillMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._original_session_local = database_module.AsyncSessionLocal
        database_module.AsyncSessionLocal = self.session_factory

    async def asyncTearDown(self):
        database_module.AsyncSessionLocal = self._original_session_local
        await self.engine.dispose()

    async def test_backfill_dry_run_matches_real_backfill(self):
        async with self.session_factory() as session:
            project = Project(name="Legacy")
            session.add(project)
            await session.flush()
            session.add(UserStory(project_id=project.id, as_a="user", i_want="plan", so_that="ship"))
            session.add(TestSpec(project_id=project.id, description="spec"))
            session.add(Task(project_id=project.id, title="task", description="desc"))
            session.add(ArchitectureDecision(project_id=project.id, title="ADR", decision="Keep it simple"))
            session.add(Message(project_id=project.id, role="assistant", content="hello", role_tab="ba"))
            await session.commit()

        dry_run = await _backfill_feature_scoping(dry_run=True)
        real_run = await _backfill_feature_scoping(dry_run=False)

        self.assertEqual(dry_run[0]["stories"], real_run[0]["stories"])
        self.assertEqual(dry_run[0]["test_specs"], real_run[0]["test_specs"])
        self.assertEqual(dry_run[0]["tasks"], real_run[0]["tasks"])

        async with self.session_factory() as session:
            feature_rows = (await session.execute(select(models_db.Feature))).scalars().all()
            self.assertEqual(len(feature_rows), 1)
            feature_id = feature_rows[0].id

            story = (await session.execute(select(UserStory))).scalar_one()
            spec = (await session.execute(select(TestSpec))).scalar_one()
            task = (await session.execute(select(Task))).scalar_one()
            decision = (await session.execute(select(ArchitectureDecision))).scalar_one()
            message = (await session.execute(select(Message))).scalar_one()

            self.assertEqual(story.feature_id, feature_id)
            self.assertEqual(spec.feature_id, feature_id)
            self.assertEqual(task.feature_id, feature_id)
            self.assertEqual(message.feature_id, feature_id)
            self.assertIsNone(decision.feature_id)


if __name__ == "__main__":
    unittest.main()
