"""Tests for role-execution-trace persistence (M0)."""
from __future__ import annotations

import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401 — registers ORM models
from models.db import Project, RoleExecutionTrace
from services.llm.evaluators import NullEvaluator
from services.llm.react_loop import (
    ActorOutput,
    EvaluationResult,
    build_actor_output,
)
from services.llm.trace_store import (
    deserialize_actor_output,
    get_traces_for_project,
    persist_iteration_trace,
    record_single_turn,
)


class TracePersistenceTests(unittest.IsolatedAsyncioTestCase):
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

    async def _make_project(self, session) -> Project:
        project = Project(name="tp")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def test_record_single_turn_writes_one_final_row(self):
        async with self.session_factory() as session:
            project = await self._make_project(session)

            output = build_actor_output(
                text="hello world",
                tool_calls=[{"name": "add_user_story", "result": "ok"}],
            )

            await record_single_turn(
                session,
                project_id=project.id,
                role="ba",
                actor_prompt="what is the problem?",
                actor_output=output,
                evaluator=NullEvaluator(role="ba"),
            )

            rows = await get_traces_for_project(session, project.id)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row.role, "ba")
            self.assertEqual(row.iteration, 1)
            self.assertTrue(row.final)
            self.assertEqual(row.evaluator_score, 1.0)
            self.assertEqual(row.rubric_version, "null-0")

            restored = deserialize_actor_output(row.actor_output)
            self.assertEqual(restored["text"], "hello world")
            self.assertEqual(len(restored["tool_calls"]), 1)

    async def test_persist_multiple_iterations_preserves_order(self):
        async with self.session_factory() as session:
            project = await self._make_project(session)

            for i in range(1, 4):
                await persist_iteration_trace(
                    session,
                    project_id=project.id,
                    role="architect",
                    iteration=i,
                    actor_prompt="plan",
                    actor_output=ActorOutput(text=f"try {i}"),
                    evaluator_result=EvaluationResult(
                        score=0.5 if i < 3 else 0.9,
                        passed=(i == 3),
                        critique="needs more detail" if i < 3 else "",
                        rubric_version="test-1",
                    ),
                    final=(i == 3),
                )

            rows = await get_traces_for_project(session, project.id, role="architect")
            # Ordered DESC by created_at → iter 3 first
            iterations = [r.iteration for r in rows]
            self.assertEqual(set(iterations), {1, 2, 3})
            finals = [r for r in rows if r.final]
            self.assertEqual(len(finals), 1)
            self.assertEqual(finals[0].iteration, 3)

    async def test_role_filter(self):
        async with self.session_factory() as session:
            project = await self._make_project(session)

            for role in ("ba", "ba", "architect"):
                await record_single_turn(
                    session,
                    project_id=project.id,
                    role=role,
                    actor_prompt="x",
                    actor_output=build_actor_output(text=""),
                    evaluator=NullEvaluator(role=role),
                )

            ba_rows = await get_traces_for_project(session, project.id, role="ba")
            arch_rows = await get_traces_for_project(session, project.id, role="architect")
            self.assertEqual(len(ba_rows), 2)
            self.assertEqual(len(arch_rows), 1)

    async def test_trace_scoped_to_project(self):
        async with self.session_factory() as session:
            p1 = await self._make_project(session)
            p2 = await self._make_project(session)

            await record_single_turn(
                session,
                project_id=p1.id,
                role="ba",
                actor_prompt="",
                actor_output=build_actor_output(text="p1 output"),
                evaluator=NullEvaluator(role="ba"),
            )
            await record_single_turn(
                session,
                project_id=p2.id,
                role="ba",
                actor_prompt="",
                actor_output=build_actor_output(text="p2 output"),
                evaluator=NullEvaluator(role="ba"),
            )

            p1_rows = await get_traces_for_project(session, p1.id)
            self.assertEqual(len(p1_rows), 1)
            restored = deserialize_actor_output(p1_rows[0].actor_output)
            self.assertEqual(restored["text"], "p1 output")


if __name__ == "__main__":
    unittest.main()
