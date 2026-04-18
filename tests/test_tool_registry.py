import unittest

from services.llm import get_phase_tool_names


class ToolRegistryTests(unittest.TestCase):
    def test_pm_phase_exposes_mvp_scope_tool(self):
        tool_names = get_phase_tool_names("pm")
        self.assertIn("set_mvp_scope", tool_names)
        self.assertIn("add_epic", tool_names)

    def test_review_phase_can_update_user_stories(self):
        tool_names = get_phase_tool_names("review")
        self.assertIn("update_user_story", tool_names)
