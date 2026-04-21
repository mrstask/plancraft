from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Project
from models.domain import (
    AddRoadmapItemArgs,
    AddTechStackEntryArgs,
    SetProjectMissionArgs,
    compute_phase_status,
)
from services.knowledge import KnowledgeService
from services.llm.trace_store import record_single_turn
from services.llm.react_loop import build_actor_output
from services.llm.evaluators.founder_evaluator import FounderEvaluator, FounderState


class FounderFlowTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_founder_artifacts_unlock_ba_after_evaluator_pass(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.commit()
            await session.refresh(project)

            svc = KnowledgeService(session)
            await svc.set_project_mission(
                project.id,
                SetProjectMissionArgs(
                    statement="Help product teams turn ideas into a clear delivery plan.",
                    target_users="product teams",
                    problem="Planning context is fragmented across disconnected docs and chats.",
                ),
            )
            await svc.add_roadmap_item(
                project.id,
                AddRoadmapItemArgs(
                    title="Ship the core planning loop",
                    description="Launch the first framing workflow so product teams can define, review, and align a project end to end.",
                    mvp=True,
                ),
            )
            await svc.add_tech_stack_entry(
                project.id,
                AddTechStackEntryArgs(
                    layer="backend",
                    choice="FastAPI",
                    rationale="It keeps the service Python-native, fits the current codebase, and is simple to extend while the product framing is still evolving.",
                ),
            )
            await svc.add_tech_stack_entry(
                project.id,
                AddTechStackEntryArgs(
                    layer="frontend",
                    choice="Server-rendered HTMX UI",
                    rationale="It keeps the interface lightweight, works well with the existing templates, and avoids unnecessary frontend complexity in v1.",
                ),
            )

            async def load_state(_project_id: str) -> FounderState:
                mission = await svc.get_project_mission(project.id)
                roadmap = await svc.get_all_roadmap_items(project.id)
                tech = await svc.get_all_tech_stack_entries(project.id)
                return FounderState(
                    mission_statement=mission.statement if mission else "",
                    mission_target_users=mission.target_users if mission else "",
                    mission_problem=mission.problem if mission else "",
                    roadmap_items=[
                        {"title": item.title, "description": item.description, "mvp": bool(item.mvp)}
                        for item in roadmap
                    ],
                    tech_stack_entries=[
                        {"layer": entry.layer, "choice": entry.choice, "rationale": entry.rationale}
                        for entry in tech
                    ],
                )

            await record_single_turn(
                session,
                project_id=project.id,
                role="founder",
                actor_prompt="founder framing",
                actor_output=build_actor_output(text="saved founder artifacts"),
                evaluator=FounderEvaluator(_loader_fn=load_state),
            )

            snapshot = await svc.get_snapshot(project.id)
            phases = compute_phase_status(snapshot)
            by_key = {phase.key: phase for phase in phases}

            self.assertTrue(by_key["founder"].complete)
            self.assertTrue(by_key["ba"].unlocked)
            self.assertEqual(snapshot.roadmap_item_count, 1)
            self.assertEqual(snapshot.tech_stack_count, 2)

    async def test_legacy_project_seed_creates_founder_drafts(self):
        async with self.session_factory() as session:
            project = Project(
                name="Legacy Planner",
                description="Teams need a better way to plan delivery.",
                business_goals=["Reduce time spent aligning on project scope"],
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)

            svc = KnowledgeService(session)
            message = await svc.seed_founder_from_existing_project(project.id)

            mission = await svc.get_project_mission(project.id)
            roadmap = await svc.get_all_roadmap_items(project.id)
            tech = await svc.get_all_tech_stack_entries(project.id)

            self.assertIn("seeded", message.lower())
            self.assertIsNotNone(mission)
            self.assertGreaterEqual(len(roadmap), 1)
            self.assertGreaterEqual(len(tech), 1)
