"""End-to-end integration test for the planning flow.

Drives the FastAPI app over HTTP with an in-memory SQLite DB and a temp
workspace root. Each step simulates the user clarifying questions / filling
the phase panel, then validates both database artifacts and the rendered
docs-as-code files.

Currently covers step 1 (Founder phase). Further steps (BA / PM / Architect /
TDD / Review) will be appended to the same `IntegrationFlowTests` class so the
whole flow builds up incrementally on a single project.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import database as database_module
from config import settings
from database import Base, get_db
from main import app
from models import db as models_db  # noqa: F401 — registers all ORM models
from models.db import Project
from models.domain import compute_phase_status
from services.knowledge import KnowledgeService
from services.llm.evaluators.founder_evaluator import FounderEvaluator, FounderState
from services.llm.react_loop import build_actor_output
from services.llm.trace_store import record_single_turn


PROJECT_NAME = "Memo Cards"


class IntegrationFlowTests(unittest.IsolatedAsyncioTestCase):
    """Integration test that walks a single project through every phase."""

    async def asyncSetUp(self):
        # Isolated DB per test — use StaticPool so every connection sees the same schema.
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Background workspace renders open their own session via
        # `database.AsyncSessionLocal`. Point that at the in-memory engine so
        # fire-and-forget renders hit the test DB, not the real planning.db.
        self._original_async_session_local = database_module.AsyncSessionLocal
        database_module.AsyncSessionLocal = self.session_factory

        # Isolated workspace root — so the test doesn't pollute ./projects/.
        self.workspace_root = Path(tempfile.mkdtemp(prefix="plancraft-it-"))
        self._original_projects_root = settings.projects_root
        settings.projects_root = self.workspace_root

        async def _override_get_db():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        )

    async def asyncTearDown(self):
        # Let pending fire-and-forget renders finish before we tear down the engine.
        import asyncio as _asyncio
        pending = [t for t in _asyncio.all_tasks() if t is not _asyncio.current_task()]
        if pending:
            await _asyncio.gather(*pending, return_exceptions=True)

        await self.client.aclose()
        app.dependency_overrides.pop(get_db, None)
        database_module.AsyncSessionLocal = self._original_async_session_local
        settings.projects_root = self._original_projects_root
        shutil.rmtree(self.workspace_root, ignore_errors=True)
        await self.engine.dispose()

    # -------------- helpers --------------

    async def _create_project(self, name: str = PROJECT_NAME) -> str:
        resp = await self.client.post("/projects", data={"name": name, "creation_mode": "blank"})
        self.assertEqual(resp.status_code, 303, msg=resp.text)
        location = resp.headers["location"]
        self.assertTrue(location.startswith("/projects/"))
        return location.rsplit("/", 1)[-1]

    async def _db_project(self, project_id: str) -> Project:
        async with self.session_factory() as session:
            from sqlalchemy import select
            row = await session.execute(select(Project).where(Project.id == project_id))
            project = row.scalar_one_or_none()
            self.assertIsNotNone(project, f"project {project_id} missing from DB")
            return project

    async def _mark_founder_evaluator_passed(self, project_id: str) -> None:
        """Drive the evaluator loop the same way the founder panel does on success."""
        async with self.session_factory() as session:
            svc = KnowledgeService(session)

            async def load_state(_pid: str) -> FounderState:
                mission = await svc.get_project_mission(project_id)
                roadmap = await svc.get_all_roadmap_items(project_id)
                tech = await svc.get_all_tech_stack_entries(project_id)
                return FounderState(
                    mission_statement=mission.statement if mission else "",
                    mission_target_users=mission.target_users if mission else "",
                    mission_problem=mission.problem if mission else "",
                    roadmap_items=[
                        {"title": i.title, "description": i.description, "mvp": bool(i.mvp)}
                        for i in roadmap
                    ],
                    tech_stack_entries=[
                        {"layer": e.layer, "choice": e.choice, "rationale": e.rationale}
                        for e in tech
                    ],
                )

            await record_single_turn(
                session,
                project_id=project_id,
                role="founder",
                actor_prompt="founder framing complete",
                actor_output=build_actor_output(text="saved founder artifacts"),
                evaluator=FounderEvaluator(_loader_fn=load_state),
            )

    # -------------- step 1: Founder phase --------------

    async def test_step1_founder_phase(self):
        # 1. Create the project.
        project_id = await self._create_project()

        project = await self._db_project(project_id)
        self.assertEqual(project.name, PROJECT_NAME)
        self.assertIsNotNone(project.root_path, "workspace path was not set on project")

        ws_root = Path(project.root_path)
        self.assertTrue(ws_root.exists(), "workspace directory was not created on disk")
        self.assertTrue(
            ws_root.is_relative_to(self.workspace_root),
            f"workspace {ws_root} escaped test projects_root {self.workspace_root}",
        )

        # The session page should render for the new project.
        resp = await self.client.get(f"/projects/{project_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(PROJECT_NAME, resp.text)

        # 2. Clarify: mission (statement / target users / problem).
        mission_payload = {
            "statement": (
                "Help students and lifelong learners retain what they study by turning notes "
                "into short, spaced-repetition memo cards."
            ),
            "target_users": "Self-directed learners preparing for exams or keeping technical knowledge fresh.",
            "problem": (
                "Passive re-reading forgets fast. Existing flashcard apps are heavyweight and "
                "break learners out of the tool they were taking notes in."
            ),
        }
        resp = await self.client.patch(
            f"/projects/{project_id}/founder/mission", data=mission_payload
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)

        # 3. Clarify: one MVP roadmap item + one post-MVP.
        resp = await self.client.post(
            f"/projects/{project_id}/founder/roadmap-items",
            data={
                "title": "Core spaced-repetition loop",
                "description": (
                    "Create a deck, add cards, get scheduled reviews driven by SM-2-lite so "
                    "users can reliably rehearse what they've added."
                ),
                "mvp": "on",
            },
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        resp = await self.client.post(
            f"/projects/{project_id}/founder/roadmap-items",
            data={
                "title": "Import from markdown notes",
                "description": "Paste markdown bullets and auto-split them into draft cards.",
            },
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)

        # 4. Clarify: tech-stack choices.
        for layer, choice, rationale in (
            (
                "backend",
                "FastAPI",
                "Python-native, low-ceremony, matches the existing Plancraft stack and keeps the app local-first.",
            ),
            (
                "frontend",
                "Server-rendered HTMX",
                "Keeps the UI lightweight and avoids a JS build step while the product framing is still evolving.",
            ),
            (
                "storage",
                "SQLite",
                "Single-file, zero-ops, plenty for a personal-scale study tool that ships as a local binary.",
            ),
        ):
            resp = await self.client.post(
                f"/projects/{project_id}/founder/tech-stack-entries",
                data={"layer": layer, "choice": choice, "rationale": rationale},
            )
            self.assertEqual(resp.status_code, 200, msg=resp.text)

        # 5. Drive the founder evaluator to mark the phase complete.
        await self._mark_founder_evaluator_passed(project_id)

        # ---------- validate DB artifacts ----------
        async with self.session_factory() as session:
            svc = KnowledgeService(session)
            mission = await svc.get_project_mission(project_id)
            roadmap = await svc.get_all_roadmap_items(project_id)
            tech = await svc.get_all_tech_stack_entries(project_id)
            snapshot = await svc.get_snapshot(project_id)

        self.assertIsNotNone(mission)
        self.assertIn("memo cards", mission.statement.lower())
        self.assertTrue(mission.target_users)
        self.assertTrue(mission.problem)

        self.assertEqual(len(roadmap), 2)
        self.assertTrue(any(item.mvp for item in roadmap), "no MVP roadmap item was saved")

        layers = {entry.layer for entry in tech}
        self.assertSetEqual(layers, {"backend", "frontend", "storage"})
        for entry in tech:
            self.assertTrue(entry.choice, f"empty choice on {entry.layer}")
            self.assertTrue(entry.rationale, f"empty rationale on {entry.layer}")

        # ---------- validate phase transitions ----------
        self.assertTrue(snapshot.founder_evaluator_passed)
        phases = {p.key: p for p in compute_phase_status(snapshot)}
        self.assertTrue(phases["founder"].complete, "founder phase should be complete")
        self.assertTrue(phases["ba"].unlocked, "BA phase should unlock once founder is done")
        self.assertFalse(phases["pm"].unlocked, "PM should still be locked after founder")

        # ---------- validate rendered workspace files ----------
        mission_md = ws_root / "product" / "mission.md"
        roadmap_md = ws_root / "product" / "roadmap.md"
        tech_md = ws_root / "product" / "tech-stack.md"
        self.assertTrue(mission_md.exists(), f"mission not rendered at {mission_md}")
        self.assertTrue(roadmap_md.exists(), f"roadmap not rendered at {roadmap_md}")
        self.assertTrue(tech_md.exists(), f"tech stack not rendered at {tech_md}")

        mission_text = mission_md.read_text(encoding="utf-8")
        self.assertIn("memo cards", mission_text.lower())

        roadmap_text = roadmap_md.read_text(encoding="utf-8")
        self.assertIn("Core spaced-repetition loop", roadmap_text)
        self.assertIn("Import from markdown notes", roadmap_text)

        tech_text = tech_md.read_text(encoding="utf-8")
        self.assertIn("FastAPI", tech_text)
        self.assertIn("HTMX", tech_text)
        self.assertIn("SQLite", tech_text)


if __name__ == "__main__":
    unittest.main()
