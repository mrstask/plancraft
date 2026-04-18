import unittest

from models.domain import KnowledgeSnapshot, compute_phase_status


class PhaseStatusTests(unittest.TestCase):
    def test_pm_phase_requires_epics_and_mvp_scope(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            problem_statement="Help teams plan software",
            story_count=3,
            epic_count=1,
            mvp_story_count=0,
        )

        phases = compute_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertTrue(by_key["ba"].complete)
        self.assertFalse(by_key["pm"].complete)
        self.assertFalse(by_key["architect"].unlocked)

    def test_architecture_unlocks_after_mvp_scope_is_set(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            problem_statement="Help teams plan software",
            story_count=3,
            epic_count=1,
            mvp_story_count=2,
        )

        phases = compute_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertTrue(by_key["pm"].complete)
        self.assertTrue(by_key["architect"].unlocked)
