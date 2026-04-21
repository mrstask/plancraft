import unittest

from models.domain import KnowledgeSnapshot, compute_phase_status


class PhaseStatusTests(unittest.TestCase):
    def test_ba_stays_locked_until_founder_gate_passes(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            mission_statement="Help planning teams launch projects with less friction.",
            mission_target_users="planning teams",
            mission_problem="Project setup is fragmented and inconsistent.",
            roadmap_item_count=2,
            tech_stack_count=2,
            founder_evaluator_passed=False,
        )

        phases = compute_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertFalse(by_key["founder"].complete)
        self.assertFalse(by_key["ba"].unlocked)

    def test_pm_phase_requires_epics_and_mvp_scope(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            mission_statement="Help teams plan software faster.",
            mission_target_users="product teams",
            mission_problem="Planning artifacts are fragmented.",
            roadmap_item_count=2,
            tech_stack_count=2,
            founder_evaluator_passed=True,
            problem_statement="Help teams plan software",
            story_count=3,
            epic_count=1,
            mvp_story_count=0,
            # BA gate now requires personas, flows, vision_scope, and no pending clarifications
            persona_count=1,
            flow_count=1,
            vision_scope_set=True,
            pending_clarification_ids=[],
        )

        phases = compute_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertTrue(by_key["founder"].complete)
        self.assertTrue(by_key["ba"].complete)
        self.assertFalse(by_key["pm"].complete)
        self.assertFalse(by_key["architect"].unlocked)

    def test_architecture_unlocks_after_mvp_scope_is_set(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            mission_statement="Help teams plan software faster.",
            mission_target_users="product teams",
            mission_problem="Planning artifacts are fragmented.",
            roadmap_item_count=2,
            tech_stack_count=2,
            founder_evaluator_passed=True,
            problem_statement="Help teams plan software",
            story_count=3,
            epic_count=1,
            mvp_story_count=2,
            persona_count=1,
            flow_count=1,
            vision_scope_set=True,
            pending_clarification_ids=[],
        )

        phases = compute_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertTrue(by_key["pm"].complete)
        self.assertTrue(by_key["architect"].unlocked)
