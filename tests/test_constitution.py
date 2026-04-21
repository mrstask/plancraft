"""Tests for constitution artifact — M1."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401 — registers ORM models
from models.db import Project
from services.workspace.renderers.constitution import render_constitution
from services.workspace.workspace import ProjectWorkspace


DEFAULT_CONSTITUTION_PATH = (
    Path(__file__).parent.parent
    / "services/workspace/templates/default_constitution.md"
)


class ConstitutionRendererTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.ws = ProjectWorkspace(Path(self._tmp.name))
        (Path(self._tmp.name) / ".plancraft").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_render_writes_file(self):
        md = "# Constitution\n\n## Quality rules\n- All stories must have AC.\n"
        path = render_constitution(self.ws, md)
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(encoding="utf-8"), md)

    def test_render_round_trip(self):
        original = "# Constitution\n\n## Testing\n- Every story must have a test spec.\n"
        render_constitution(self.ws, original)
        restored = self.ws.constitution_file.read_text(encoding="utf-8")
        self.assertEqual(restored, original)

    def test_default_template_exists_and_has_rules(self):
        self.assertTrue(DEFAULT_CONSTITUTION_PATH.exists(), "default_constitution.md missing")
        content = DEFAULT_CONSTITUTION_PATH.read_text(encoding="utf-8")
        self.assertIn("## Quality rules", content)
        self.assertIn("- ", content)


class ConstitutionDBTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _make_project(self, session, *, constitution_md: str = "") -> Project:
        project = Project(name="test-proj", constitution_md=constitution_md)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def test_project_stores_constitution(self):
        md = "# Constitution\n\n## Quality rules\n- All stories must have AC.\n"
        async with self.session_factory() as session:
            project = await self._make_project(session, constitution_md=md)
            self.assertEqual(project.constitution_md, md)

    async def test_project_constitution_defaults_empty(self):
        async with self.session_factory() as session:
            project = await self._make_project(session)
            self.assertEqual(project.constitution_md, "")

    async def test_constitution_update_persists(self):
        async with self.session_factory() as session:
            project = await self._make_project(session)
            project.constitution_md = "# Constitution\n\n## Testing\n- Must have tests.\n"
            await session.commit()
            await session.refresh(project)
            self.assertIn("Must have tests", project.constitution_md)


if __name__ == "__main__":
    unittest.main()
