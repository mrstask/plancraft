"""Tests for Step 3 BA update: role prompt, PHASE_TOOL_RULES, render_ba."""
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
    AnswerClarificationPointArgs,
    SetLlmInteractionModelArgs,
    SetVisionScopeArgs,
)
from roles.ba_clarifications import CATALOG, REQUIRED_IDS
from services.knowledge import KnowledgeService
from services.llm.prompts import PHASE_TOOL_RULES, build_system_prompt
from services.llm.registry import get_phase_tool_names
from services.workspace.workspace import ProjectWorkspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# BA role prompt tests
# ---------------------------------------------------------------------------

class TestBASystemPromptFragment(unittest.TestCase):
    def _fragment(self) -> str:
        from roles.business_analyst import BusinessAnalystRole
        return BusinessAnalystRole().system_prompt_fragment

    def test_fragment_contains_catalog_point_ids(self):
        fragment = self._fragment()
        for point in CATALOG:
            self.assertIn(point.id, fragment, f"Catalog point '{point.id}' missing from BA prompt")

    def test_fragment_contains_all_required_artifact_tools(self):
        fragment = self._fragment()
        expected_tools = [
            "set_problem_statement", "set_vision_scope", "add_persona",
            "add_user_flow", "add_user_story", "add_business_rule",
            "add_data_entity", "add_functional_requirement", "add_glossary_term",
            "set_llm_interaction_model", "record_constraint",
            "answer_clarification_point",
        ]
        for tool in expected_tools:
            self.assertIn(tool, fragment, f"Tool '{tool}' missing from BA prompt")

    def test_fragment_contains_completion_gate_guidance(self):
        fragment = self._fragment()
        self.assertIn("completion gate", fragment.lower())
        self.assertIn("persona", fragment.lower())
        self.assertIn("user flow", fragment.lower())

    def test_fragment_contains_elicitation_principles(self):
        fragment = self._fragment()
        self.assertIn("ONE focused question", fragment)
        self.assertIn("push back", fragment.lower())

    def test_trigger_keywords_include_new_ba_terms(self):
        from roles.business_analyst import BusinessAnalystRole
        keywords = BusinessAnalystRole().trigger_keywords
        for term in ("persona", "flow", "rule", "entity", "scope"):
            self.assertIn(term, keywords, f"Trigger keyword '{term}' missing")

    def test_clarification_guide_covers_optional_points(self):
        fragment = self._fragment()
        optional_ids = [p.id for p in CATALOG if not p.required]
        for pid in optional_ids:
            self.assertIn(pid, fragment, f"Optional point '{pid}' missing from guide")


# ---------------------------------------------------------------------------
# PHASE_TOOL_RULES["ba"] tests
# ---------------------------------------------------------------------------

class TestBAPhaseToolRules(unittest.TestCase):
    def _rules(self) -> str:
        return PHASE_TOOL_RULES["ba"]

    def test_rules_cover_all_new_ba_tools(self):
        rules = self._rules()
        expected = [
            "set_vision_scope", "add_persona", "add_user_flow", "add_business_rule",
            "add_data_entity", "add_functional_requirement", "add_glossary_term",
            "set_llm_interaction_model", "answer_clarification_point",
        ]
        for tool in expected:
            self.assertIn(tool, rules, f"Tool '{tool}' missing from PHASE_TOOL_RULES[ba]")

    def test_rules_retain_original_tools(self):
        rules = self._rules()
        for tool in ("set_problem_statement", "add_user_story", "update_user_story", "record_constraint"):
            self.assertIn(tool, rules)

    def test_rules_include_conversational_reply_reminder(self):
        self.assertIn("visible text response", self._rules())


# ---------------------------------------------------------------------------
# build_system_prompt for BA phase
# ---------------------------------------------------------------------------

class TestBuildSystemPromptBA(unittest.TestCase):
    def _build(self, pending_ids=None) -> str:
        from models.domain import KnowledgeSnapshot
        snap = KnowledgeSnapshot(
            project_name="Demo",
            problem_statement="Reduce planning overhead",
            pending_clarification_ids=pending_ids or ["problem_goals", "personas_roles"],
        )
        return build_system_prompt(snap, role_tab="ba")

    def test_prompt_identifies_role(self):
        prompt = self._build()
        self.assertIn("Business Analyst", prompt)

    def test_prompt_includes_pending_clarifications_in_context(self):
        prompt = self._build(pending_ids=["problem_goals"])
        self.assertIn("problem_goals", prompt)

    def test_prompt_includes_tool_rules(self):
        prompt = self._build()
        self.assertIn("answer_clarification_point", prompt)

    def test_prompt_includes_project_state(self):
        prompt = self._build()
        self.assertIn("Demo", prompt)
        self.assertIn("Reduce planning overhead", prompt)


# ---------------------------------------------------------------------------
# render_ba role-context file tests
# ---------------------------------------------------------------------------

class TestRenderBA(AsyncBase):
    async def test_render_ba_empty_project(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("BA Context", content)
        self.assertIn("Problem Statement", content)
        self.assertIn("Not yet defined", content)
        self.assertIn("Clarification Points", content)
        self.assertIn("pending", content)

    async def test_render_ba_shows_pending_clarification_ids(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            # Answer one required point so the list shrinks by 1
            await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="problem_goals", answer="Reduce planning time."),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertNotIn("problem_goals", content)
        # Others still pending
        self.assertIn("personas_roles", content)

    async def test_render_ba_shows_vision_scope(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.set_vision_scope(
                project.id,
                SetVisionScopeArgs(
                    business_goals=["reduce planning time"],
                    in_scope=["BA chat", "project creation"],
                    out_of_scope=["billing"],
                ),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("reduce planning time", content)
        self.assertIn("BA chat", content)
        self.assertIn("billing", content)
        self.assertNotIn("Not yet populated", content)

    async def test_render_ba_shows_personas(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_persona(
                project.id,
                AddPersonaArgs(name="Power User", role="Developer", goals=["ship fast"], pain_points=["too much setup"]),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("Power User", content)
        self.assertIn("Developer", content)
        self.assertIn("ship fast", content)
        self.assertIn("too much setup", content)

    async def test_render_ba_shows_user_flow_steps(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_user_flow(
                project.id,
                AddUserFlowArgs(
                    name="Create project",
                    steps=["User: opens dashboard", "User: clicks New Project", "System: creates project"],
                ),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("Create project", content)
        self.assertIn("opens dashboard", content)
        self.assertIn("User:", content)
        self.assertIn("System:", content)

    async def test_render_ba_shows_business_rules(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_business_rule(
                project.id,
                AddBusinessRuleArgs(rule="Project needs at least one story", applies_to=["Project"]),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("Project needs at least one story", content)
        self.assertIn("applies to: Project", content)

    async def test_render_ba_shows_data_entities(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_data_entity(
                project.id,
                AddDataEntityArgs(
                    name="Project",
                    attributes=["id: UUID", "name: str"],
                    relationships=["has many UserStories"],
                ),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("Project", content)
        self.assertIn("id: UUID", content)
        self.assertIn("has many UserStories", content)

    async def test_render_ba_shows_functional_requirements(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_functional_requirement(
                project.id,
                AddFunctionalRequirementArgs(
                    description="System must allow users to create a project",
                    inputs=["project name"],
                    outputs=["project ID"],
                ),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("System must allow users to create a project", content)
        self.assertIn("project name", content)
        self.assertIn("project ID", content)

    async def test_render_ba_shows_glossary(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_glossary_term(
                project.id,
                AddGlossaryTermArgs(term="workspace", definition="Project artifact directory"),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("workspace", content)
        self.assertIn("Project artifact directory", content)

    async def test_render_ba_shows_llm_interaction_model(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.set_llm_interaction_model(
                project.id,
                SetLlmInteractionModelArgs(
                    llm_role="BA agent",
                    interaction_pattern="multi-turn loop",
                    input_format="user messages",
                    output_format="tool calls",
                    memory_strategy="snapshot per turn",
                    error_handling=["retry once"],
                ),
            )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("LLM Interaction Model", content)
        self.assertIn("BA agent", content)
        self.assertIn("multi-turn loop", content)
        self.assertIn("retry once", content)

    async def test_render_ba_all_sections_present_empty(self):
        """All section headers appear even when artifacts are missing."""
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        for section in (
            "Vision & Scope", "Clarification Points", "Personas",
            "User Flows", "Business Rules", "Data Entities",
            "Functional Requirements", "Constraints", "Glossary",
        ):
            self.assertIn(section, content, f"Section '{section}' missing from BA context")

    async def test_render_ba_all_required_clarifications_answered_shows_done(self):
        from services.workspace.role_context import render_ba
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            for pid in REQUIRED_IDS:
                await svc.answer_clarification_point(
                    project.id,
                    AnswerClarificationPointArgs(point_id=pid, answer="answered"),
                )
            path = await render_ba(self.ws, project.id, session)
            content = path.read_text()

        self.assertIn("All required clarification points answered", content)
        self.assertIn("0 pending", content)


if __name__ == "__main__":
    unittest.main()
