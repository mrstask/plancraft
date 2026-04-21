import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from services.workspace.renderers.adrs_split import render_split_adrs
from services.workspace.workspace import ProjectWorkspace


class AdrSplitRenderingTests(unittest.TestCase):
    def test_feature_local_and_cross_cutting_adrs_render_once_each(self):
        tmp = tempfile.mkdtemp()
        ws = ProjectWorkspace(Path(tmp))
        ws.scaffold()

        feature = MagicMock()
        feature.id = "feature-1"
        feature.ordinal = 1
        feature.slug = "checkout"

        cross_cutting = MagicMock()
        cross_cutting.title = "Use PostgreSQL"
        cross_cutting.context = "Need reliable transactions"
        cross_cutting.decision = "Use PostgreSQL for primary storage"
        cross_cutting.consequences = {}
        cross_cutting.created_at = None
        cross_cutting.feature_id = None

        feature_local = MagicMock()
        feature_local.title = "Stripe Webhooks"
        feature_local.context = "Payment state must stay synchronized"
        feature_local.decision = "Consume Stripe webhooks for payment updates"
        feature_local.consequences = {}
        feature_local.created_at = None
        feature_local.feature_id = feature.id

        paths = render_split_adrs(ws, [cross_cutting, feature_local], {feature.id: feature})

        root_adr = ws.adr_file(1, cross_cutting.title)
        feature_adr = ws.feature_adr_file(feature, 1, feature_local.title)

        self.assertEqual(len(paths), 2)
        self.assertTrue(root_adr.exists())
        self.assertTrue(feature_adr.exists())
        self.assertIn("Use PostgreSQL", root_adr.read_text())
        self.assertIn("Stripe Webhooks", feature_adr.read_text())


if __name__ == "__main__":
    unittest.main()
