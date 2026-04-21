"""Integration tests for Step 2 BA update: commands, queries, snapshot, registry."""
import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401 — registers all ORM models
from models.db import Project
from models.domain import (
    AddBusinessRuleArgs,
    AddDataEntityArgs,
    AddFunctionalRequirementArgs,
    AddGlossaryTermArgs,
    AddPersonaArgs,
    AddUserFlowArgs,
    AddUserStoryArgs,
    AnswerClarificationPointArgs,
    SetLlmInteractionModelArgs,
    SetVisionScopeArgs,
)
from services.knowledge import KnowledgeService
from services.llm.registry import (
    ALL_TOOLS,
    TOOL_ALIASES,
    get_phase_tool_names,
)


# ---------------------------------------------------------------------------
# Shared async test base
# ---------------------------------------------------------------------------

class AsyncBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def make_project(self, session, name="TestProject") -> Project:
        p = Project(name=name)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p


# ---------------------------------------------------------------------------
# Command handler tests
# ---------------------------------------------------------------------------

class TestBACommands(AsyncBase):
    async def test_set_vision_scope_persists(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.set_vision_scope(
                project.id,
                SetVisionScopeArgs(
                    business_goals=["reduce planning time"],
                    success_metrics=["90% of projects complete in under 30 min"],
                    in_scope=["project creation", "BA chat"],
                    out_of_scope=["billing", "SSO"],
                    target_users=["software teams"],
                ),
            )
            self.assertEqual(result, "Vision & Scope updated.")
            refreshed = await svc._get_project(project.id)
            self.assertEqual(refreshed.business_goals, ["reduce planning time"])
            self.assertEqual(len(refreshed.out_of_scope), 2)

    async def test_add_persona_creates_and_upserts(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)

            r1 = await svc.add_persona(
                project.id,
                AddPersonaArgs(name="Admin", role="System Administrator", goals=["manage users"]),
            )
            self.assertIn("added", r1)

            r2 = await svc.add_persona(
                project.id,
                AddPersonaArgs(name="admin", role="System Administrator", goals=["manage users", "view reports"]),
            )
            self.assertIn("updated", r2)

            personas = await svc.get_all_personas(project.id)
            self.assertEqual(len(personas), 1)
            self.assertEqual(personas[0].goals, ["manage users", "view reports"])

    async def test_add_user_flow_with_steps(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.add_user_flow(
                project.id,
                AddUserFlowArgs(
                    name="Create project",
                    steps=[
                        "User: opens dashboard",
                        "User: clicks New Project",
                        "System: shows creation form",
                        "User: fills name and submits",
                        "System: creates project and redirects",
                    ],
                ),
            )
            self.assertIn("5 steps", result)
            flows = await svc.get_all_user_flows(project.id)
            self.assertEqual(len(flows), 1)
            self.assertEqual(len(flows[0].steps), 5)
            self.assertEqual(flows[0].steps[0].actor, "User")
            self.assertEqual(flows[0].steps[0].description, "opens dashboard")

    async def test_add_user_flow_upserts_steps(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_user_flow(
                project.id,
                AddUserFlowArgs(name="Login", steps=["Enter credentials", "Submit"]),
            )
            await svc.add_user_flow(
                project.id,
                AddUserFlowArgs(name="login", steps=["Open app", "Enter credentials", "Submit", "Redirected"]),
            )
            flows = await svc.get_all_user_flows(project.id)
            self.assertEqual(len(flows), 1)
            self.assertEqual(len(flows[0].steps), 4)

    async def test_add_business_rule(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.add_business_rule(
                project.id,
                AddBusinessRuleArgs(
                    rule="A project must have at least one story before PM phase",
                    applies_to=["Project"],
                ),
            )
            self.assertIn("added", result)
            rules = await svc.get_all_business_rules(project.id)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].applies_to, ["Project"])

    async def test_add_business_rule_upserts(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            rule_text = "A project must have at least one story before PM phase"
            await svc.add_business_rule(project.id, AddBusinessRuleArgs(rule=rule_text))
            await svc.add_business_rule(
                project.id,
                AddBusinessRuleArgs(rule=rule_text, applies_to=["Project", "PM Phase"]),
            )
            rules = await svc.get_all_business_rules(project.id)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].applies_to, ["Project", "PM Phase"])

    async def test_add_data_entity(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.add_data_entity(
                project.id,
                AddDataEntityArgs(
                    name="Project",
                    attributes=["id: UUID", "name: str", "created_at: datetime"],
                    relationships=["has many UserStories", "has many Personas"],
                ),
            )
            self.assertIn("added", result)
            entities = await svc.get_all_data_entities(project.id)
            self.assertEqual(len(entities), 1)
            self.assertEqual(len(entities[0].attributes), 3)

    async def test_add_functional_requirement_links_story(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            story_result = await svc.add_user_story(
                project.id,
                AddUserStoryArgs(as_a="planner", i_want="create project", so_that="I can track work"),
            )
            story_id = story_result.split(": ", 1)[1]

            result = await svc.add_functional_requirement(
                project.id,
                AddFunctionalRequirementArgs(
                    description="System must allow users to create a project",
                    inputs=["project name", "description"],
                    outputs=["project ID"],
                    related_user_stories=[story_id],
                ),
            )
            self.assertIn("added", result)
            frs = await svc.get_all_functional_requirements(project.id)
            self.assertEqual(len(frs), 1)

    async def test_add_glossary_term_creates_and_updates(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_glossary_term(
                project.id,
                AddGlossaryTermArgs(term="workspace", definition="A folder for project artifacts"),
            )
            await svc.add_glossary_term(
                project.id,
                AddGlossaryTermArgs(term="WORKSPACE", definition="Updated: project artifact directory"),
            )
            refreshed = await svc._get_project(project.id)
            terms = refreshed.terminology
            self.assertEqual(len(terms), 1)
            self.assertEqual(terms[0]["definition"], "Updated: project artifact directory")

    async def test_set_llm_interaction_model(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.set_llm_interaction_model(
                project.id,
                SetLlmInteractionModelArgs(
                    llm_role="BA agent",
                    interaction_pattern="multi-turn clarification loop",
                    input_format="user messages",
                    output_format="structured tool calls",
                    memory_strategy="snapshot per turn",
                    error_handling=["retry once", "surface error"],
                ),
            )
            self.assertEqual(result, "LLM interaction model set.")
            refreshed = await svc._get_project(project.id)
            self.assertEqual(refreshed.llm_interaction_model["llm_role"], "BA agent")

    async def test_answer_clarification_point_creates_and_updates(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            r1 = await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="problem_goals", answer="We reduce planning overhead."),
            )
            self.assertIn("answered", r1)

            r2 = await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="problem_goals", answer="Refined answer.", status="answered"),
            )
            self.assertIn("answered", r2)

    async def test_answer_clarification_point_unknown_id(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="nonexistent_id", answer="x"),
            )
            self.assertIn("Unknown", result)

    async def test_answer_clarification_point_skip(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            result = await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="llm_interaction", answer="", status="skipped"),
            )
            self.assertIn("skipped", result)


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------

class TestSnapshotBuilderBAFields(AsyncBase):
    async def test_snapshot_counts_ba_artifacts(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_persona(project.id, AddPersonaArgs(name="User", role="End user"))
            await svc.add_user_flow(project.id, AddUserFlowArgs(name="Login", steps=["Step 1"]))
            await svc.add_business_rule(project.id, AddBusinessRuleArgs(rule="Must have story"))
            await svc.add_data_entity(project.id, AddDataEntityArgs(name="Project"))

            snap = await svc.get_snapshot(project.id)
            self.assertEqual(snap.persona_count, 1)
            self.assertEqual(snap.flow_count, 1)
            self.assertEqual(snap.business_rule_count, 1)
            self.assertEqual(snap.entity_count, 1)

    async def test_snapshot_vision_scope_set_flag(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            snap_before = await svc.get_snapshot(project.id)
            self.assertFalse(snap_before.vision_scope_set)

            await svc.set_vision_scope(
                project.id,
                SetVisionScopeArgs(business_goals=["reduce planning time"]),
            )
            snap_after = await svc.get_snapshot(project.id)
            self.assertTrue(snap_after.vision_scope_set)

    async def test_snapshot_pending_clarifications_shrink_as_answered(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)

            snap_initial = await svc.get_snapshot(project.id)
            initial_count = len(snap_initial.pending_clarification_ids)
            self.assertGreater(initial_count, 0)

            await svc.answer_clarification_point(
                project.id,
                AnswerClarificationPointArgs(point_id="problem_goals", answer="Solved."),
            )
            snap_after = await svc.get_snapshot(project.id)
            self.assertEqual(len(snap_after.pending_clarification_ids), initial_count - 1)
            self.assertNotIn("problem_goals", snap_after.pending_clarification_ids)

    async def test_snapshot_recent_personas_populated(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_persona(project.id, AddPersonaArgs(name="Developer", role="Engineer"))
            snap = await svc.get_snapshot(project.id)
            self.assertEqual(len(snap.recent_personas), 1)
            self.assertEqual(snap.recent_personas[0].name, "Developer")

    async def test_snapshot_recent_flows_populated(self):
        async with self.session_factory() as session:
            project = await self.make_project(session)
            svc = KnowledgeService(session)
            await svc.add_user_flow(
                project.id,
                AddUserFlowArgs(name="Create project", steps=["Step 1", "Step 2", "Step 3"]),
            )
            snap = await svc.get_snapshot(project.id)
            self.assertEqual(len(snap.recent_flows), 1)
            self.assertEqual(snap.recent_flows[0].step_count, 3)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestRegistryBATools(unittest.TestCase):
    def test_all_new_ba_tools_registered(self):
        ba_tools = get_phase_tool_names("ba")
        expected = {
            "set_problem_statement",
            "add_user_story",
            "update_user_story",
            "record_constraint",
            "set_vision_scope",
            "add_persona",
            "add_user_flow",
            "add_business_rule",
            "add_data_entity",
            "add_functional_requirement",
            "add_glossary_term",
            "set_llm_interaction_model",
            "answer_clarification_point",
        }
        self.assertEqual(ba_tools, expected)

    def test_new_ba_tools_not_available_in_other_phases(self):
        ba_only = {
            "set_vision_scope", "add_persona", "add_user_flow", "add_business_rule",
            "add_data_entity", "add_functional_requirement", "add_glossary_term",
            "set_llm_interaction_model", "answer_clarification_point",
        }
        for phase in ("pm", "architect", "tdd", "review"):
            phase_tools = get_phase_tool_names(phase)
            self.assertTrue(
                ba_only.isdisjoint(phase_tools),
                f"BA-only tools leaked into phase '{phase}': {ba_only & phase_tools}",
            )

    def test_new_aliases_resolve(self):
        alias_checks = {
            "add_flow": "add_user_flow",
            "create_flow": "add_user_flow",
            "add_persona": "add_persona",  # not an alias — direct name
            "create_persona": "add_persona",
            "add_rule": "add_business_rule",
            "add_entity": "add_data_entity",
            "add_fr": "add_functional_requirement",
            "add_term": "add_glossary_term",
            "set_vision": "set_vision_scope",
            "set_scope": "set_vision_scope",
            "answer_clarification": "answer_clarification_point",
        }
        tool_names = {t.name for t in ALL_TOOLS}
        for alias, canonical in alias_checks.items():
            if alias in TOOL_ALIASES:
                self.assertEqual(TOOL_ALIASES[alias], canonical, f"Alias {alias} wrong")
            # canonical must exist
            self.assertIn(canonical, tool_names, f"Canonical tool '{canonical}' not registered")

    def test_tool_schemas_are_valid_dicts(self):
        ba_tool_names = get_phase_tool_names("ba")
        for tool in ALL_TOOLS:
            if tool.name in ba_tool_names:
                schema = tool.schema()
                self.assertIn("type", schema)
                self.assertIn("function", schema)
                self.assertIn("parameters", schema["function"])


if __name__ == "__main__":
    unittest.main()
