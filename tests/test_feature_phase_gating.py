import unittest

from models.domain import KnowledgeSnapshot, compute_feature_phase_status


class FeaturePhaseGatingTests(unittest.TestCase):
    def test_feature_architect_unlocks_after_feature_has_stories(self):
        snapshot = KnowledgeSnapshot(
            project_name="Demo",
            feature_id="feature-1",
            feature_title="Onboarding",
            feature_story_count=2,
            feature_test_spec_count=0,
            feature_task_count=0,
            feature_decision_count=0,
        )

        phases = compute_feature_phase_status(snapshot)
        by_key = {phase.key: phase for phase in phases}

        self.assertTrue(by_key["ba"].complete)
        self.assertTrue(by_key["architect"].unlocked)
        self.assertFalse(by_key["tdd"].unlocked)

    def test_feature_loop_starts_locked_until_feature_exists(self):
        snapshot = KnowledgeSnapshot(project_name="Demo")
        phases = compute_feature_phase_status(snapshot)
        self.assertFalse(phases[0].unlocked)


if __name__ == "__main__":
    unittest.main()
