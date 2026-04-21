from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base
from models import db as models_db  # noqa: F401
from models.db import Project, TechStackEntry
from services.profiles import ProfileCommands, ProfileQueries


class ProjectInheritTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._tmp = tempfile.TemporaryDirectory()
        self._original_profiles_root = settings.profiles_root
        settings.profiles_root = Path(self._tmp.name)

    async def asyncTearDown(self):
        settings.profiles_root = self._original_profiles_root
        self._tmp.cleanup()
        await self.engine.dispose()

    async def test_create_project_from_profile_then_diverge_independently(self):
        async with self.session_factory() as session:
            commands = ProfileCommands(session)
            profile = await commands.create_profile(
                name="Rails SaaS",
                description="Profile for SaaS-style web apps.",
                version="1.2.0",
                constitution_md="# Constitution\n\n- Prefer boring architecture.\n",
                tech_stack_entries=[
                    {"layer": "frontend", "choice": "Server-rendered UI", "rationale": "Fast iteration."},
                    {"layer": "backend", "choice": "FastAPI", "rationale": "Simple Python service."},
                ],
                conventions={"naming": {"style": "explicit"}},
            )

            project = Project(name="Acme Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            await commands.inherit_profile_into_project(project.id, profile.id)
            await session.commit()
            await session.refresh(project)

            tech_rows = await session.execute(
                select(TechStackEntry).where(TechStackEntry.project_id == project.id).order_by(TechStackEntry.layer.asc())
            )
            tech_stack = tech_rows.scalars().all()

            self.assertEqual(project.constitution_md, profile.constitution_md)
            self.assertEqual(project.profile_ref, "Rails SaaS@1.2.0")
            self.assertEqual(len(tech_stack), 2)

            project.constitution_md = "# Constitution\n\n- Diverged for this project only.\n"
            await session.commit()

            stored_profile = await ProfileQueries(session).get_profile(profile.id)
            self.assertEqual(stored_profile.constitution_md, "# Constitution\n\n- Prefer boring architecture.\n")

            await commands.update_profile(
                profile.id,
                name="Rails SaaS",
                description=profile.description,
                version="1.3.0",
                constitution_md="# Constitution\n\n- Updated profile baseline.\n",
                tech_stack_entries=[
                    {"layer": "backend", "choice": "Django", "rationale": "Alternative baseline."}
                ],
                conventions={"naming": {"style": "explicit"}},
            )
            await session.refresh(project)

            self.assertEqual(project.constitution_md, "# Constitution\n\n- Diverged for this project only.\n")


if __name__ == "__main__":
    unittest.main()
