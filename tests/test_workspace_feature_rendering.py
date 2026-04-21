from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from services.workspace.renderers.feature_plan import render_feature_plan
from services.workspace.renderers.feature_spec import render_feature_spec
from services.workspace.renderers.feature_tasks import render_feature_tasks
from services.workspace.workspace import ProjectWorkspace


class WorkspaceFeatureRenderingTests(unittest.TestCase):
    def test_feature_renderers_write_specs_directory(self):
        tmp = tempfile.mkdtemp()
        ws = ProjectWorkspace(Path(tmp))
        ws.scaffold()

        feature = MagicMock()
        feature.ordinal = 2
        feature.slug = "payments"
        feature.title = "Payments"
        feature.description = "Let users manage subscriptions."
        feature.status = "drafting"

        story = MagicMock()
        story.id = "story-1"
        story.as_a = "user"
        story.i_want = "pay"
        story.so_that = "subscribe"
        ac = MagicMock()
        ac.criterion = "Payment succeeds"
        story.acceptance_criteria = [ac]

        component = MagicMock()
        component.name = "Billing API"
        component.component_type = "service"
        component.responsibility = "Processes subscriptions"

        decision = MagicMock()
        decision.title = "Stripe"
        decision.decision = "Use Stripe Checkout"

        task = MagicMock()
        task.title = "Implement webhook handler"
        task.complexity = "medium"
        task.description = "Persist billing events"

        spec_path = render_feature_spec(ws, feature, [story])
        plan_path = render_feature_plan(ws, feature, [component], [decision])
        tasks_path = render_feature_tasks(ws, feature, [task])

        self.assertTrue(spec_path.exists())
        self.assertTrue(plan_path.exists())
        self.assertTrue(tasks_path.exists())
        self.assertEqual(spec_path.parent.name, "002-payments")
        self.assertIn("Feature Spec: Payments", spec_path.read_text())
        self.assertIn("Billing API", plan_path.read_text())
        self.assertIn("webhook handler", tasks_path.read_text())


if __name__ == "__main__":
    unittest.main()
