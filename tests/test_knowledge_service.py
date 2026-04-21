import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Project
from models.domain import (
    AddRoadmapItemArgs,
    AddTechStackEntryArgs,
    AddUserStoryArgs,
    SetMvpScopeArgs,
    SetProjectMissionArgs,
    UpdateUserStoryArgs,
)
from services.knowledge import KnowledgeService


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_update_user_story_replaces_acceptance_criteria(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            svc = KnowledgeService(session)
            result = await svc.add_user_story(
                project.id,
                AddUserStoryArgs(
                    as_a="planner",
                    i_want="clear tasks",
                    so_that="I can ship faster",
                    acceptance_criteria=["one", "two"],
                ),
            )
            story_id = result.split(": ", 1)[1]

            await svc.update_user_story(
                project.id,
                UpdateUserStoryArgs(
                    story_id=story_id,
                    acceptance_criteria=["updated criterion"],
                ),
            )

            story = await svc.get_story(project.id, story_id)
            self.assertEqual(
                [criterion.criterion for criterion in story.acceptance_criteria],
                ["updated criterion"],
            )

    async def test_set_mvp_scope_persists_resolved_story_ids(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            svc = KnowledgeService(session)
            story_result = await svc.add_user_story(
                project.id,
                AddUserStoryArgs(
                    as_a="planner",
                    i_want="clear tasks",
                    so_that="I can ship faster",
                ),
            )
            story_id = story_result.split(": ", 1)[1]

            await svc.set_mvp_scope(
                project.id,
                SetMvpScopeArgs(
                    story_ids=[story_id[:8]],
                    rationale="Smallest valuable slice",
                ),
            )

            refreshed = await svc._get_project(project.id)
            self.assertEqual(refreshed.mvp_story_ids, [story_id])
            self.assertEqual(refreshed.mvp_rationale, "Smallest valuable slice")

    async def test_artifact_detail_queries_are_scoped_to_project(self):
        async with self.session_factory() as session:
            project_a = Project(name="A")
            project_b = Project(name="B")
            session.add_all([project_a, project_b])
            await session.commit()
            await session.refresh(project_a)
            await session.refresh(project_b)

            svc = KnowledgeService(session)
            story_result = await svc.add_user_story(
                project_a.id,
                AddUserStoryArgs(
                    as_a="planner",
                    i_want="clear tasks",
                    so_that="I can ship faster",
                ),
            )
            story_id = story_result.split(": ", 1)[1]

            self.assertIsNotNone(await svc.get_story(project_a.id, story_id))
            self.assertIsNone(await svc.get_story(project_b.id, story_id))

    async def test_founder_artifacts_are_persisted(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            svc = KnowledgeService(session)
            await svc.set_project_mission(
                project.id,
                SetProjectMissionArgs(
                    statement="Help product teams turn ideas into a delivery plan.",
                    target_users="product teams",
                    problem="Planning context is spread across disconnected docs.",
                ),
            )
            await svc.add_roadmap_item(
                project.id,
                AddRoadmapItemArgs(
                    title="Launch the planning workflow",
                    description="Ship the first planning flow and validate that teams can frame a project end to end.",
                    mvp=True,
                ),
            )
            await svc.add_tech_stack_entry(
                project.id,
                AddTechStackEntryArgs(
                    layer="backend",
                    choice="FastAPI",
                    rationale="It matches the team's Python stack, supports quick iteration, and keeps the service model simple for v1.",
                ),
            )

            mission = await svc.get_project_mission(project.id)
            roadmap = await svc.get_all_roadmap_items(project.id)
            tech = await svc.get_all_tech_stack_entries(project.id)

            self.assertEqual(mission.target_users, "product teams")
            self.assertEqual(len(roadmap), 1)
            self.assertTrue(roadmap[0].mvp)
            self.assertEqual(tech[0].choice, "FastAPI")
