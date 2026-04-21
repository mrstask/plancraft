from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import ArchitectureDecision, Project
from models.domain import AddTestSpecArgs, AddUserStoryArgs, ProposeTaskArgs, RecordDecisionArgs
from services.features import FeatureCommands
from services.knowledge import KnowledgeService


class FeatureScopedQueryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_feature_scope_isolates_artifacts_but_keeps_cross_cutting_decisions(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            feature_commands = FeatureCommands(session)
            feature_a = await feature_commands.create_feature(project.id, title="Onboarding")
            feature_b = await feature_commands.create_feature(project.id, title="Billing")

            feature_a_svc = KnowledgeService(session, feature_id=feature_a.id)
            feature_b_svc = KnowledgeService(session, feature_id=feature_b.id)
            project_svc = KnowledgeService(session)

            await feature_a_svc.add_user_story(project.id, AddUserStoryArgs(as_a="user", i_want="sign up", so_that="start"))
            await feature_a_svc.add_test_spec(project.id, AddTestSpecArgs(description="signup works"))
            await feature_a_svc.propose_task(project.id, ProposeTaskArgs(title="Implement signup", description="Build it"))
            await feature_a_svc.record_decision(project.id, RecordDecisionArgs(title="Signup flow", decision="Use email link"))

            await feature_b_svc.add_user_story(project.id, AddUserStoryArgs(as_a="user", i_want="pay", so_that="subscribe"))
            await project_svc.record_decision(project.id, RecordDecisionArgs(title="Shared auth", decision="Keep auth centralized"))

            a_stories = await feature_a_svc.get_all_stories(project.id)
            b_stories = await feature_b_svc.get_all_stories(project.id)
            a_specs = await feature_a_svc.get_all_test_specs(project.id)
            a_tasks = await feature_a_svc.get_all_tasks(project.id)
            a_decisions = await feature_a_svc.get_all_decisions(project.id)

            self.assertEqual(len(a_stories), 1)
            self.assertEqual(len(b_stories), 1)
            self.assertEqual(len(a_specs), 1)
            self.assertEqual(len(a_tasks), 1)
            self.assertEqual({item.title for item in a_decisions}, {"Signup flow", "Shared auth"})


if __name__ == "__main__":
    unittest.main()
