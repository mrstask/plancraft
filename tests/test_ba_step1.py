"""Tests for Step 1 BA update: domain models, phase gate, clarification catalog."""
import unittest

from models.domain import (
    KnowledgeSnapshot,
    AddPersonaArgs,
    AddUserFlowArgs,
    AddBusinessRuleArgs,
    AddDataEntityArgs,
    AddFunctionalRequirementArgs,
    AddGlossaryTermArgs,
    SetVisionScopeArgs,
    SetLlmInteractionModelArgs,
    AnswerClarificationPointArgs,
    compute_phase_status,
)
from roles.ba_clarifications import (
    CATALOG,
    CATALOG_BY_ID,
    REQUIRED_IDS,
    get_point,
    get_required_ids,
)


class TestNewArgModels(unittest.TestCase):
    def test_add_persona_defaults(self):
        p = AddPersonaArgs(name="Power User", role="Developer")
        self.assertEqual(p.goals, [])
        self.assertEqual(p.pain_points, [])

    def test_add_persona_full(self):
        p = AddPersonaArgs(
            name="Admin",
            role="System Administrator",
            goals=["manage users", "view reports"],
            pain_points=["too many manual steps"],
        )
        self.assertEqual(len(p.goals), 2)

    def test_add_user_flow_defaults(self):
        f = AddUserFlowArgs(name="Create project")
        self.assertEqual(f.steps, [])

    def test_add_user_flow_with_steps(self):
        f = AddUserFlowArgs(
            name="Login flow",
            steps=["User opens app", "User enters credentials", "System validates", "User sees dashboard"],
        )
        self.assertEqual(len(f.steps), 4)

    def test_add_business_rule(self):
        r = AddBusinessRuleArgs(rule="A project must have at least one story before PM phase", applies_to=["Project"])
        self.assertEqual(r.applies_to, ["Project"])

    def test_add_data_entity_defaults(self):
        e = AddDataEntityArgs(name="Project")
        self.assertEqual(e.attributes, [])
        self.assertEqual(e.relationships, [])

    def test_add_functional_requirement(self):
        fr = AddFunctionalRequirementArgs(
            description="System must allow users to create a project",
            inputs=["project name", "description"],
            outputs=["project ID", "confirmation message"],
            related_user_stories=["story-1"],
        )
        self.assertEqual(len(fr.inputs), 2)

    def test_add_glossary_term(self):
        t = AddGlossaryTermArgs(term="workspace", definition="A folder containing project artifacts")
        self.assertEqual(t.term, "workspace")

    def test_set_vision_scope(self):
        v = SetVisionScopeArgs(
            business_goals=["reduce planning time by 50%"],
            success_metrics=["90% of projects complete BA in under 30 min"],
            in_scope=["project creation", "BA chat"],
            out_of_scope=["billing", "SSO"],
            target_users=["software teams"],
        )
        self.assertEqual(len(v.out_of_scope), 2)

    def test_set_llm_interaction_model(self):
        m = SetLlmInteractionModelArgs(
            llm_role="Business Analyst agent",
            interaction_pattern="multi-turn clarification loop",
            input_format="user messages in conversation",
            output_format="structured artifacts via tool calls",
            memory_strategy="project knowledge snapshot injected each turn",
            error_handling=["if tool call fails, retry once then surface error to user"],
        )
        self.assertEqual(len(m.error_handling), 1)

    def test_answer_clarification_point_defaults(self):
        a = AnswerClarificationPointArgs(point_id="problem_goals", answer="We solve planning overhead.")
        self.assertEqual(a.status, "answered")

    def test_answer_clarification_point_skipped(self):
        a = AnswerClarificationPointArgs(point_id="llm_interaction", answer="", status="skipped")
        self.assertEqual(a.status, "skipped")


class TestKnowledgeSnapshotBAFields(unittest.TestCase):
    def _base(self, **kwargs) -> KnowledgeSnapshot:
        defaults = dict(
            project_name="Demo",
            problem_statement="Solve planning overhead",
            story_count=3,
            persona_count=0,
            flow_count=0,
            vision_scope_set=False,
            pending_clarification_ids=[],
        )
        defaults.update(kwargs)
        return KnowledgeSnapshot(**defaults)

    def test_context_string_includes_ba_artifacts(self):
        snap = self._base(persona_count=2, flow_count=1, fr_count=3)
        ctx = snap.to_context_string()
        self.assertIn("2 personas", ctx)
        self.assertIn("1 flows", ctx)
        self.assertIn("3 functional requirements", ctx)

    def test_context_string_shows_pending_clarifications(self):
        snap = self._base(pending_clarification_ids=["problem_goals", "personas_roles"])
        ctx = snap.to_context_string()
        self.assertIn("Pending clarifications: problem_goals, personas_roles", ctx)

    def test_context_string_shows_vision_scope_set(self):
        snap = self._base(vision_scope_set=True)
        ctx = snap.to_context_string()
        self.assertIn("Vision & Scope: populated", ctx)

    def test_recent_personas_in_context(self):
        from models.domain import PersonaSnapshot
        snap = self._base(
            persona_count=1,
            recent_personas=[PersonaSnapshot(name="Admin", role="System Administrator")],
        )
        ctx = snap.to_context_string()
        self.assertIn("Admin (System Administrator)", ctx)

    def test_recent_flows_in_context(self):
        from models.domain import FlowSnapshot
        snap = self._base(
            flow_count=1,
            recent_flows=[FlowSnapshot(name="Create project", step_count=4)],
        )
        ctx = snap.to_context_string()
        self.assertIn("Create project (4 steps)", ctx)


class TestComputePhaseStatusNewGate(unittest.TestCase):
    def _full_ba_snapshot(self, **overrides) -> KnowledgeSnapshot:
        defaults = dict(
            project_name="Demo",
            mission_statement="Help teams plan software with less overhead.",
            mission_target_users="software teams",
            mission_problem="Planning context is fragmented.",
            roadmap_item_count=2,
            tech_stack_count=2,
            founder_evaluator_passed=True,
            problem_statement="Solve planning overhead",
            story_count=3,
            persona_count=1,
            flow_count=1,
            vision_scope_set=True,
            pending_clarification_ids=[],
        )
        defaults.update(overrides)
        return KnowledgeSnapshot(**defaults)

    def test_ba_done_when_all_required_fields_present(self):
        snap = self._full_ba_snapshot()
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertTrue(phases["ba"].complete)

    def test_ba_not_done_without_persona(self):
        snap = self._full_ba_snapshot(persona_count=0)
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertFalse(phases["ba"].complete)

    def test_ba_not_done_without_flow(self):
        snap = self._full_ba_snapshot(flow_count=0)
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertFalse(phases["ba"].complete)

    def test_ba_not_done_without_vision_scope(self):
        snap = self._full_ba_snapshot(vision_scope_set=False)
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertFalse(phases["ba"].complete)

    def test_ba_not_done_with_pending_clarifications(self):
        snap = self._full_ba_snapshot(pending_clarification_ids=["problem_goals"])
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertFalse(phases["ba"].complete)

    def test_pm_locked_when_ba_not_done(self):
        snap = self._full_ba_snapshot(persona_count=0)
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertFalse(phases["pm"].unlocked)

    def test_pm_unlocked_when_ba_done(self):
        snap = self._full_ba_snapshot()
        phases = {p.key: p for p in compute_phase_status(snap)}
        self.assertTrue(phases["pm"].unlocked)

    def test_old_snapshot_without_new_fields_defaults_ba_not_done(self):
        # Simulates a pre-existing snapshot before the BA update
        snap = KnowledgeSnapshot(
            project_name="Legacy",
            problem_statement="Old problem",
            story_count=5,
        )
        phases = {p.key: p for p in compute_phase_status(snap)}
        # persona_count=0, flow_count=0 => ba_done=False — no regression for old projects
        self.assertFalse(phases["ba"].complete)


class TestClarificationCatalog(unittest.TestCase):
    def test_catalog_has_expected_points(self):
        ids = {p.id for p in CATALOG}
        expected = {
            "problem_goals", "personas_roles", "core_user_flow", "key_features",
            "user_stories", "inputs_outputs", "llm_interaction", "data_entities",
            "business_rules", "edge_cases", "nfr_lightweight", "scope_boundaries",
            "terminology",
        }
        self.assertEqual(ids, expected)

    def test_required_ids_subset_of_catalog(self):
        all_ids = {p.id for p in CATALOG}
        self.assertTrue(REQUIRED_IDS.issubset(all_ids))

    def test_all_required_points_have_nonempty_fields(self):
        for point in CATALOG:
            if point.required:
                self.assertTrue(point.question_to_user, f"{point.id} has empty question")
                self.assertTrue(point.artifact_mapping, f"{point.id} has no artifact_mapping")
                self.assertTrue(point.validation_rules, f"{point.id} has no validation_rules")

    def test_get_point_by_id(self):
        p = get_point("problem_goals")
        self.assertIsNotNone(p)
        self.assertEqual(p.id, "problem_goals")

    def test_get_point_unknown_returns_none(self):
        self.assertIsNone(get_point("nonexistent"))

    def test_get_required_ids_matches_required_flag(self):
        required = get_required_ids()
        for point in CATALOG:
            if point.required:
                self.assertIn(point.id, required)
            else:
                self.assertNotIn(point.id, required)

    def test_llm_interaction_is_optional(self):
        p = get_point("llm_interaction")
        self.assertFalse(p.required)

    def test_nfr_is_optional(self):
        p = get_point("nfr_lightweight")
        self.assertFalse(p.required)

    def test_terminology_is_optional(self):
        p = get_point("terminology")
        self.assertFalse(p.required)

    def test_catalog_frozen_and_immutable(self):
        p = get_point("problem_goals")
        with self.assertRaises((AttributeError, TypeError)):
            p.required = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
