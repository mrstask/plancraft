"""Tests for Step 5: BA renderers, export bundle, workspace dirs."""
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Project
from models.domain import (
    AddBusinessRuleArgs,
    AddDataEntityArgs,
    AddFunctionalRequirementArgs,
    AddGlossaryTermArgs,
    AddPersonaArgs,
    AddUserFlowArgs,
    AddUserStoryArgs,
    SetLlmInteractionModelArgs,
    SetVisionScopeArgs,
)
from services.knowledge import KnowledgeService
from services.workspace.workspace import ProjectWorkspace


class AsyncBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def make_project(self, session, name="TestProject") -> Project:
        p = Project(name=name)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p


# ---------------------------------------------------------------------------
# Workspace path helpers
# ---------------------------------------------------------------------------

class TestWorkspaceBADir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def test_ba_dir_created_on_scaffold(self):
        self.assertTrue(self.ws.ba_dir.is_dir())

    def test_ba_file_returns_correct_path(self):
        path = self.ws.ba_file("vision_scope.json")
        self.assertEqual(path.parent, self.ws.ba_dir)
        self.assertEqual(path.name, "vision_scope.json")

    def test_ba_dir_inside_docs(self):
        self.assertEqual(self.ws.ba_dir, self.ws.root / "docs" / "ba")


# ---------------------------------------------------------------------------
# Individual renderer tests
# ---------------------------------------------------------------------------

class TestVisionScopeRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_project(self, **kwargs):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.description = kwargs.get("description", "Reduce planning overhead")
        p.business_goals = kwargs.get("business_goals", ["reduce time"])
        p.success_metrics = kwargs.get("success_metrics", ["90% complete in 30 min"])
        p.in_scope = kwargs.get("in_scope", ["BA chat"])
        p.out_of_scope = kwargs.get("out_of_scope", ["billing"])
        p.target_users = kwargs.get("target_users", ["software teams"])
        return p

    def test_writes_json_and_md(self):
        from services.workspace.renderers.vision_scope import render_vision_scope
        json_path, md_path = render_vision_scope(self.ws, self._make_project())
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

    def test_json_schema_matches_template(self):
        from services.workspace.renderers.vision_scope import render_vision_scope
        json_path, _ = render_vision_scope(self.ws, self._make_project())
        doc = json.loads(json_path.read_text())
        for key in ("problem_statement", "target_users", "business_goals", "success_metrics",
                    "in_scope", "out_of_scope"):
            self.assertIn(key, doc, f"Key '{key}' missing from vision_scope.json")

    def test_md_contains_content(self):
        from services.workspace.renderers.vision_scope import render_vision_scope
        _, md_path = render_vision_scope(self.ws, self._make_project())
        content = md_path.read_text()
        self.assertIn("reduce time", content)
        self.assertIn("billing", content)
        self.assertIn("BA chat", content)

    def test_empty_fields_handled(self):
        from services.workspace.renderers.vision_scope import render_vision_scope
        from unittest.mock import MagicMock
        p = MagicMock()
        p.description = None
        p.business_goals = []
        p.success_metrics = []
        p.in_scope = []
        p.out_of_scope = []
        p.target_users = []
        json_path, md_path = render_vision_scope(self.ws, p)
        doc = json.loads(json_path.read_text())
        self.assertEqual(doc["business_goals"], [])
        self.assertIn("Not yet defined", md_path.read_text())


class TestPersonasRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_persona(self, name, role, goals=None, pain_points=None):
        from unittest.mock import MagicMock
        p = MagicMock()
        p.name = name
        p.role = role
        p.goals = goals or []
        p.pain_points = pain_points or []
        return p

    def test_writes_json_and_md(self):
        from services.workspace.renderers.personas import render_personas
        p = self._make_persona("Admin", "System Administrator", goals=["manage users"])
        json_path, md_path = render_personas(self.ws, [p])
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

    def test_json_schema_matches_template(self):
        from services.workspace.renderers.personas import render_personas
        p = self._make_persona("Admin", "Sys Admin", goals=["x"], pain_points=["y"])
        json_path, _ = render_personas(self.ws, [p])
        doc = json.loads(json_path.read_text())
        self.assertIsInstance(doc, list)
        self.assertEqual(len(doc), 1)
        for key in ("name", "role", "goals", "pain_points"):
            self.assertIn(key, doc[0])

    def test_empty_list_renders_placeholder(self):
        from services.workspace.renderers.personas import render_personas
        _, md_path = render_personas(self.ws, [])
        self.assertIn("No personas defined", md_path.read_text())


class TestUserFlowsRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_flow(self, name, steps_raw):
        from unittest.mock import MagicMock
        flow = MagicMock()
        flow.id = "flow-1"
        flow.name = name
        flow.description = ""
        flow.steps = []
        for i, raw in enumerate(steps_raw):
            step = MagicMock()
            step.order_index = i
            if ":" in raw:
                actor, _, desc = raw.partition(":")
                step.actor = actor.strip()
                step.description = desc.strip()
            else:
                step.actor = None
                step.description = raw
            flow.steps.append(step)
        return flow

    def test_writes_json_and_md(self):
        from services.workspace.renderers.flows import render_user_flows
        flow = self._make_flow("Login", ["User: opens app", "System: shows form"])
        json_path, md_path = render_user_flows(self.ws, [flow])
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())

    def test_json_schema_matches_template(self):
        from services.workspace.renderers.flows import render_user_flows
        flow = self._make_flow("Login", ["Step one", "Step two"])
        json_path, _ = render_user_flows(self.ws, [flow])
        doc = json.loads(json_path.read_text())
        self.assertIsInstance(doc, list)
        for key in ("id", "name", "steps"):
            self.assertIn(key, doc[0])
        self.assertEqual(len(doc[0]["steps"]), 2)

    def test_actor_prefix_preserved_in_json(self):
        from services.workspace.renderers.flows import render_user_flows
        flow = self._make_flow("Create project", ["User: clicks button", "System: responds"])
        json_path, _ = render_user_flows(self.ws, [flow])
        doc = json.loads(json_path.read_text())
        self.assertIn("User:", doc[0]["steps"][0])
        self.assertIn("System:", doc[0]["steps"][1])

    def test_md_numbered_steps(self):
        from services.workspace.renderers.flows import render_user_flows
        flow = self._make_flow("Flow", ["A", "B", "C"])
        _, md_path = render_user_flows(self.ws, [flow])
        content = md_path.read_text()
        self.assertIn("1. A", content)
        self.assertIn("3. C", content)


class TestBusinessRulesRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_rule(self, rule, applies_to=None):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.id = "rule-1"
        r.rule = rule
        r.applies_to = applies_to or []
        return r

    def test_json_schema_matches_template(self):
        from services.workspace.renderers.business_rules import render_business_rules
        r = self._make_rule("Must have story", ["Project"])
        json_path, _ = render_business_rules(self.ws, [r])
        doc = json.loads(json_path.read_text())
        self.assertIsInstance(doc, list)
        for key in ("id", "rule", "applies_to"):
            self.assertIn(key, doc[0])


class TestDataModelRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_entity(self, name, attributes=None, relationships=None):
        from unittest.mock import MagicMock
        e = MagicMock()
        e.name = name
        e.attributes = attributes or []
        e.relationships = relationships or []
        return e

    def test_json_schema_has_entities_key(self):
        from services.workspace.renderers.data_model import render_data_model
        e = self._make_entity("Project", ["id: UUID"], ["has many Stories"])
        json_path, _ = render_data_model(self.ws, [e])
        doc = json.loads(json_path.read_text())
        self.assertIn("entities", doc)
        self.assertEqual(len(doc["entities"]), 1)
        for key in ("name", "attributes", "relationships"):
            self.assertIn(key, doc["entities"][0])


class TestFunctionalRequirementsRenderer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = ProjectWorkspace(Path(self.tmp))
        self.ws.scaffold()

    def _make_fr(self, description, inputs=None, outputs=None, story_links=None):
        from unittest.mock import MagicMock
        fr = MagicMock()
        fr.description = description
        fr.inputs = inputs or []
        fr.outputs = outputs or []
        fr.story_links = story_links or []
        return fr

    def test_json_schema_matches_template(self):
        from services.workspace.renderers.functional_requirements import render_functional_requirements
        fr = self._make_fr("System must allow project creation", ["name"], ["project ID"])
        json_path, _ = render_functional_requirements(self.ws, [fr])
        doc = json.loads(json_path.read_text())
        self.assertIsInstance(doc, list)
        for key in ("id", "description", "inputs", "outputs", "related_user_stories"):
            self.assertIn(key, doc[0])
        self.assertEqual(doc[0]["id"], "FR-001")

    def test_sequential_fr_ids(self):
        from services.workspace.renderers.functional_requirements import render_functional_requirements
        frs = [self._make_fr(f"FR {i}") for i in range(3)]
        json_path, _ = render_functional_requirements(self.ws, frs)
        doc = json.loads(json_path.read_text())
        ids = [entry["id"] for entry in doc]
        self.assertEqual(ids, ["FR-001", "FR-002", "FR-003"])


# ---------------------------------------------------------------------------
# BA bundle export tests
# ---------------------------------------------------------------------------

class TestBuildBABundle(AsyncBase):
    async def _seed_ba(self, session, project):
        svc = KnowledgeService(session)
        await svc.set_vision_scope(project.id, SetVisionScopeArgs(
            business_goals=["reduce planning time"],
            success_metrics=["90% in 30 min"],
            in_scope=["BA chat"],
            out_of_scope=["billing"],
            target_users=["software teams"],
        ))
        await svc.add_persona(project.id, AddPersonaArgs(
            name="Developer", role="Engineer", goals=["ship fast"], pain_points=["too much setup"],
        ))
        await svc.add_user_flow(project.id, AddUserFlowArgs(
            name="Create project", steps=["User: opens dashboard", "System: shows form"],
        ))
        await svc.add_business_rule(project.id, AddBusinessRuleArgs(
            rule="Project needs story", applies_to=["Project"],
        ))
        await svc.add_data_entity(project.id, AddDataEntityArgs(
            name="Project", attributes=["id: UUID"], relationships=["has many Stories"],
        ))
        story_r = await svc.add_user_story(project.id, AddUserStoryArgs(
            as_a="planner", i_want="create project", so_that="I can plan",
        ))
        story_id = story_r.split(": ", 1)[1]
        await svc.add_functional_requirement(project.id, AddFunctionalRequirementArgs(
            description="System must allow project creation",
            inputs=["name"],
            outputs=["project ID"],
            related_user_stories=[story_id],
        ))
        await svc.add_glossary_term(project.id, AddGlossaryTermArgs(
            term="workspace", definition="Project artifact directory",
        ))
        await svc.set_llm_interaction_model(project.id, SetLlmInteractionModelArgs(
            llm_role="BA agent",
            interaction_pattern="multi-turn",
            input_format="messages",
            output_format="tool calls",
            memory_strategy="snapshot",
            error_handling=["retry once"],
        ))

    async def test_bundle_has_all_top_level_keys(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        expected_keys = {
            "project", "exported_at", "vision_scope", "personas", "user_flows",
            "user_stories", "functional_requirements", "data_model",
            "business_rules", "llm_interaction_model", "terminology",
        }
        self.assertEqual(set(bundle.keys()), expected_keys)

    async def test_vision_scope_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        vs = bundle["vision_scope"]
        for key in ("problem_statement", "target_users", "business_goals",
                    "success_metrics", "in_scope", "out_of_scope"):
            self.assertIn(key, vs)
        self.assertEqual(vs["business_goals"], ["reduce planning time"])
        self.assertEqual(vs["out_of_scope"], ["billing"])

    async def test_personas_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["personas"]), 1)
        p = bundle["personas"][0]
        for key in ("name", "role", "goals", "pain_points"):
            self.assertIn(key, p)
        self.assertEqual(p["name"], "Developer")

    async def test_user_flows_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["user_flows"]), 1)
        flow = bundle["user_flows"][0]
        for key in ("id", "name", "steps"):
            self.assertIn(key, flow)
        self.assertEqual(len(flow["steps"]), 2)

    async def test_user_stories_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["user_stories"]), 1)
        s = bundle["user_stories"][0]
        for key in ("id", "actor", "action", "value", "acceptance_criteria", "priority", "dependencies"):
            self.assertIn(key, s)
        self.assertEqual(s["id"], "US-001")

    async def test_functional_requirements_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["functional_requirements"]), 1)
        fr = bundle["functional_requirements"][0]
        for key in ("id", "description", "inputs", "outputs", "related_user_stories"):
            self.assertIn(key, fr)
        self.assertEqual(fr["id"], "FR-001")

    async def test_data_model_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        dm = bundle["data_model"]
        self.assertIn("entities", dm)
        self.assertEqual(len(dm["entities"]), 1)
        for key in ("name", "attributes", "relationships"):
            self.assertIn(key, dm["entities"][0])

    async def test_business_rules_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["business_rules"]), 1)
        for key in ("id", "rule", "applies_to"):
            self.assertIn(key, bundle["business_rules"][0])

    async def test_llm_interaction_model_schema(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        llm = bundle["llm_interaction_model"]
        for key in ("llm_role", "interaction_pattern", "input_format",
                    "output_format", "memory_strategy", "error_handling"):
            self.assertIn(key, llm)
        self.assertEqual(llm["llm_role"], "BA agent")

    async def test_terminology_present(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            await self._seed_ba(session, project)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(len(bundle["terminology"]), 1)
        self.assertEqual(bundle["terminology"][0]["term"], "workspace")

    async def test_empty_project_bundle_is_valid(self):
        from services.export_service import build_ba_bundle
        async with self.session_factory() as session:
            project = await self.make_project(session)
            bundle = await build_ba_bundle(project.id, session)

        self.assertEqual(bundle["personas"], [])
        self.assertEqual(bundle["user_flows"], [])
        self.assertEqual(bundle["data_model"]["entities"], [])
        llm = bundle["llm_interaction_model"]
        self.assertEqual(llm["llm_role"], "")
        self.assertEqual(llm["error_handling"], [])


# ---------------------------------------------------------------------------
# Arc42 glossary fix
# ---------------------------------------------------------------------------

class TestArc42GlossaryFix(AsyncBase):
    async def test_arc42_glossary_uses_real_terminology(self):
        from services.export_service import build_arc42
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            project.root_path = None  # just need DB; arc42 doesn't need workspace
            await svc.add_glossary_term(
                project.id,
                AddGlossaryTermArgs(term="workspace", definition="Project artifact folder"),
            )
            arc42_md = await build_arc42(project.id, session)

        self.assertIn("workspace", arc42_md)
        self.assertIn("Project artifact folder", arc42_md)
        self.assertNotIn("> *Not yet captured.*", arc42_md.split("## 12.")[1])


if __name__ == "__main__":
    unittest.main()
