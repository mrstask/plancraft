"""Tests for the M6 pluggable export interface."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401 — registers ORM models
from models.db import (
    AcceptanceCriterion,
    ArchitectureDecision,
    Component,
    Constraint,
    Epic,
    Project,
    Task,
    TestSpec,
    UserStory,
)
from services.export.targets import TARGETS, get_target
from services.export.targets.base import BuildResult
from services.export.validators import run_validator
from services.export.validators.arc42_validator import Arc42Validator, EXPECTED_SECTIONS
from services.export_service import build_export


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_project(session) -> Project:
    project = Project(
        name="Test Project",
        description="A test problem statement.",
        constitution_md="# Constitution\n\n## Quality rules\n- All stories must have AC.\n",
    )
    session.add(project)
    await session.flush()

    epic = Epic(project_id=project.id, title="Core")
    session.add(epic)
    await session.flush()

    story = UserStory(
        project_id=project.id,
        epic_id=epic.id,
        as_a="user",
        i_want="export my project",
        so_that="agents can consume it",
        priority="must",
    )
    session.add(story)
    await session.flush()

    ac = AcceptanceCriterion(story_id=story.id, criterion="Export produces a valid zip.")
    session.add(ac)

    comp = Component(
        project_id=project.id,
        name="ExportService",
        responsibility="Builds export bundles",
        component_type="service",
    )
    session.add(comp)

    decision = ArchitectureDecision(
        project_id=project.id,
        title="Use pluggable targets",
        context="Need to support multiple formats",
        decision="Implement ExportTarget protocol",
    )
    session.add(decision)

    constraint = Constraint(
        project_id=project.id,
        type="technical",
        description="Output must be deterministic.",
    )
    session.add(constraint)

    spec = TestSpec(
        project_id=project.id,
        description="Export produces arc42.md",
        test_type="unit",
        given_context="a project with stories",
        when_action="export_arc42 is called",
        then_expectation="arc42.md has 12 sections",
    )
    session.add(spec)

    task = Task(
        project_id=project.id,
        title="Implement export service",
        description="Build the pluggable export interface.",
        complexity="medium",
    )
    session.add(task)

    await session.commit()
    await session.refresh(project)
    return project


class ExportTargetRegistryTests(unittest.TestCase):
    def test_all_expected_targets_registered(self):
        names = {t.name for t in TARGETS}
        self.assertIn("arc42", names)
        self.assertIn("tasks", names)
        self.assertIn("ba", names)
        self.assertIn("workspace", names)

    def test_get_target_returns_correct_instance(self):
        t = get_target("arc42")
        self.assertEqual(t.name, "arc42")
        self.assertEqual(t.display_name, "arc42 Architecture Doc")

    def test_get_target_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_target("does-not-exist")

    def test_all_targets_have_required_attrs(self):
        for target in TARGETS:
            self.assertTrue(hasattr(target, "name"))
            self.assertTrue(hasattr(target, "display_name"))
            self.assertTrue(hasattr(target, "description"))
            self.assertTrue(callable(getattr(target, "build", None)))


class Arc42ValidatorTests(unittest.TestCase):
    def _make_result(self, content: str, tmp_dir: Path) -> BuildResult:
        f = tmp_dir / "arc42.md"
        f.write_text(content, encoding="utf-8")
        result = BuildResult(out_dir=tmp_dir)
        result.add_file(f)
        return result

    def test_valid_arc42_passes(self):
        with TemporaryDirectory() as tmp:
            sections = "\n\n".join(f"## {n}. Section {n}\n\nContent." for n in range(1, 13))
            result = self._make_result(sections, Path(tmp))
            errors = Arc42Validator().validate(result)
            self.assertEqual(errors, [])

    def test_missing_sections_flagged(self):
        with TemporaryDirectory() as tmp:
            # only sections 1-10
            sections = "\n\n".join(f"## {n}. Section {n}\n\nContent." for n in range(1, 11))
            result = self._make_result(sections, Path(tmp))
            errors = Arc42Validator().validate(result)
            self.assertEqual(len(errors), 1)
            self.assertIn("11", errors[0])
            self.assertIn("12", errors[0])

    def test_no_arc42_file_returns_error(self):
        with TemporaryDirectory() as tmp:
            result = BuildResult(out_dir=Path(tmp))
            errors = Arc42Validator().validate(result)
            self.assertEqual(len(errors), 1)
            self.assertIn("not found", errors[0])

    def test_run_validator_sets_schema_fields(self):
        with TemporaryDirectory() as tmp:
            sections = "\n\n".join(f"## {n}. Section {n}\n\nContent." for n in range(1, 13))
            p = Path(tmp) / "arc42.md"
            p.write_text(sections, encoding="utf-8")
            result = BuildResult(out_dir=Path(tmp))
            result.add_file(p)
            result = run_validator("arc42", result)
            self.assertTrue(result.schema_valid)
            self.assertEqual(result.schema_errors, [])

    def test_run_validator_no_validator_passes(self):
        with TemporaryDirectory() as tmp:
            result = BuildResult(out_dir=Path(tmp))
            result = run_validator("tasks", result)
            self.assertTrue(result.schema_valid)


class ExportTargetBuildTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_arc42_target_produces_file(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                target = get_target("arc42")
                result = await target.build(project.id, out_dir, session)
                self.assertEqual(len(result.files_written), 1)
                self.assertEqual(result.files_written[0].name, "arc42.md")
                content = result.files_written[0].read_text(encoding="utf-8")
                self.assertIn("## 1.", content)
                self.assertIn("## 12.", content)

    async def test_arc42_target_validates_cleanly(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                result = await build_export("arc42", project.id, out_dir, session)
                self.assertTrue(result.schema_valid)
                self.assertEqual(result.schema_errors, [])

    async def test_tasks_target_produces_json(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                target = get_target("tasks")
                result = await target.build(project.id, out_dir, session)
                self.assertEqual(result.files_written[0].name, "tasks.json")
                payload = json.loads(result.files_written[0].read_text())
                self.assertIn("tasks", payload)
                self.assertIn("project", payload)

    async def test_ba_target_produces_json(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                target = get_target("ba")
                result = await target.build(project.id, out_dir, session)
                self.assertEqual(result.files_written[0].name, "ba_bundle.json")
                payload = json.loads(result.files_written[0].read_text())
                self.assertIn("user_stories", payload)
                self.assertIn("personas", payload)

    async def test_build_export_returns_build_result(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp:
                out_dir = Path(tmp)
                result = await build_export("tasks", project.id, out_dir, session)
                self.assertIsInstance(result, BuildResult)
                self.assertTrue(result.schema_valid)

    async def test_build_export_unknown_target_raises(self):
        async with self.session_factory() as session:
            project = await _seed_project(session)
            with TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                await build_export("does-not-exist", project.id, Path(tmp), session)


if __name__ == "__main__":
    unittest.main()
