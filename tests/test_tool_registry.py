import unittest

from services.llm import get_phase_tool_names


class ToolRegistryTests(unittest.TestCase):
    def test_founder_phase_exposes_product_triage_tools(self):
        tool_names = get_phase_tool_names("founder")
        self.assertIn("set_project_mission", tool_names)
        self.assertIn("add_roadmap_item", tool_names)
        self.assertIn("add_tech_stack_entry", tool_names)

    def test_pm_phase_exposes_mvp_scope_tool(self):
        tool_names = get_phase_tool_names("pm")
        self.assertIn("set_mvp_scope", tool_names)
        self.assertIn("add_epic", tool_names)

    def test_review_phase_can_update_user_stories(self):
        tool_names = get_phase_tool_names("review")
        self.assertIn("update_user_story", tool_names)
