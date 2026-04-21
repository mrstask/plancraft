import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Feature, Project
from models.domain import AnswerClarificationPointArgs
from services.knowledge import KnowledgeService
from services.workspace.renderers.research import render_research
from services.workspace.workspace import ProjectWorkspace


class ResearchRenderingTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_feature_clarifications_render_to_research_markdown(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.flush()
            feature = Feature(project_id=project.id, slug="payments", ordinal=2, title="Payments")
            session.add(feature)
            await session.commit()

            svc = KnowledgeService(session, feature_id=feature.id)
            await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(
                    point_id="problem_goals",
                    answer="Reduce payment setup time for returning customers.",
                ),
            )
            await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(
                    point_id="personas_roles",
                    answer="Finance admins manage billing while end users confirm purchases.",
                ),
            )

            tmp = tempfile.mkdtemp()
            ws = ProjectWorkspace(Path(tmp))
            ws.scaffold()

            path = render_research(ws, feature, await svc.get_all_clarification_points(project.id))
            text = path.read_text()

            self.assertTrue(path.exists())
            self.assertEqual(path, ws.feature_research_file(feature))
            self.assertIn("Research: Payments", text)
            self.assertIn("Reduce payment setup time", text)
            self.assertIn("personas_roles", text)

            project_scope = KnowledgeService(session)
            self.assertEqual(await project_scope.get_all_clarification_points(project.id), [])


if __name__ == "__main__":
    unittest.main()
