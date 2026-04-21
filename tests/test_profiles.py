from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base
from models import db as models_db  # noqa: F401
from services.profiles import ProfileCommands, ProfileQueries, parse_tech_stack_template


class ProfileCrudTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_profile_crud_syncs_db_and_disk(self):
        async with self.session_factory() as session:
            commands = ProfileCommands(session)
            queries = ProfileQueries(session)

            profile = await commands.create_profile(
                name="Python Web Team",
                description="Reusable defaults for Python web products.",
                constitution_md="# Constitution\n\n## Quality rules\n- Keep it simple.\n",
                tech_stack_entries=[
                    {
                        "layer": "backend",
                        "choice": "FastAPI",
                        "rationale": "Good fit for async Python services.",
                    }
                ],
                conventions={"reviews": {"focus": "bugs"}},
            )

            stored = await queries.get_profile(profile.id)
            self.assertIsNotNone(stored)
            self.assertEqual(stored.name, "Python Web Team")
            self.assertEqual(len(parse_tech_stack_template(stored.tech_stack_template)), 1)

            mirror = settings.profiles_root / "python-web-team"
            self.assertTrue((mirror / "constitution.md").exists())
            self.assertTrue((mirror / "tech-stack.yml").exists())
            self.assertTrue((mirror / "conventions.json").exists())
            self.assertTrue((mirror / "profile.yml").exists())

            updated = await commands.update_profile(
                profile.id,
                name="Python Web Platform",
                description="Updated description",
                version="1.2.0",
                constitution_md="# Constitution\n\n## Quality rules\n- Ship thin slices.\n",
                tech_stack_entries=[
                    {
                        "layer": "frontend",
                        "choice": "HTMX",
                        "rationale": "Keeps the UI close to the server.",
                    }
                ],
                conventions={"docs": {"style": "brief"}},
            )

            self.assertEqual(updated.name, "Python Web Platform")
            self.assertFalse((settings.profiles_root / "python-web-team").exists())
            self.assertTrue((settings.profiles_root / "python-web-platform" / "profile.yml").exists())

    async def test_starter_profiles_seed_on_first_run(self):
        async with self.session_factory() as session:
            commands = ProfileCommands(session)
            created = await commands.ensure_starter_profiles()
            listed = await ProfileQueries(session).list_profiles()

            self.assertGreaterEqual(len(created), 3)
            self.assertGreaterEqual(len(listed), 3)
            self.assertTrue((settings.profiles_root / "generic-product" / "profile.yml").exists())

    async def test_duplicate_name_is_rejected(self):
        async with self.session_factory() as session:
            commands = ProfileCommands(session)
            await commands.create_profile(name="CLI Tool", constitution_md="# Constitution\n")

            with self.assertRaises(ValueError):
                await commands.create_profile(name="CLI Tool", constitution_md="# Other\n")


if __name__ == "__main__":
    unittest.main()
