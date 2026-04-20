"""Tests for the workspace scaffold, renderers, and role-context files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# ProjectWorkspace path helpers
# ---------------------------------------------------------------------------

class TestProjectWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _make_ws(self):
        from services.workspace.workspace import ProjectWorkspace
        ws = ProjectWorkspace(Path(self.tmp))
        ws.scaffold()
        return ws

    def test_scaffold_creates_all_dirs(self):
        ws = self._make_ws()
        expected = [
            "docs/arc42",
            "docs/adr",
            "docs/stories",
            "docs/c4",
            "docs/diagrams",
            "tests/specs",
            "tasks",
            ".plancraft/role-context",
        ]
        for rel in expected:
            self.assertTrue((ws.root / rel).is_dir(), f"Missing dir: {rel}")

    def test_scaffold_is_idempotent(self):
        ws = self._make_ws()
        # calling scaffold again must not raise
        ws.scaffold()
        self.assertTrue((ws.root / "docs/arc42").is_dir())

    def test_well_known_paths(self):
        ws = self._make_ws()
        self.assertEqual(ws.readme.name, "README.md")
        self.assertEqual(ws.c4_workspace.name, "workspace.dsl")
        self.assertEqual(ws.tasks_json.name, "tasks.json")
        self.assertEqual(ws.spec_file(1).name, "SPEC-001.md")
        self.assertEqual(ws.task_file(3).name, "TASK-003.md")
        self.assertEqual(ws.story_file(7).name, "US-007.md")
        self.assertEqual(ws.role_context_file("ba").name, "ba.md")

    def test_create_slugifies_name(self):
        import os
        from unittest.mock import patch
        from services.workspace.workspace import ProjectWorkspace

        with tempfile.TemporaryDirectory() as root:
            from config import settings
            original = settings.projects_root
            settings.projects_root = Path(root)
            try:
                ws = ProjectWorkspace.create("My Cool Project!!", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
                self.assertTrue(ws.root.name.startswith("my-cool-project-"))
                self.assertTrue(ws.root.exists())
            finally:
                settings.projects_root = original


# ---------------------------------------------------------------------------
# Arc42 section renderers
# ---------------------------------------------------------------------------

class TestArc42Renderers(unittest.TestCase):
    def _make_ws(self):
        from services.workspace.workspace import ProjectWorkspace
        tmp = Path(tempfile.mkdtemp())
        ws = ProjectWorkspace(tmp)
        ws.scaffold()
        return ws

    def _minimal_data(self):
        from services.export.queries import Arc42ExportData
        return Arc42ExportData(
            project_name="Test Project",
            problem_statement="We need to test things.",
            constraints=[],
            components=[],
            decisions=[],
            stories=[],
            specs=[],
            tasks=[],
        )

    def test_render_all_produces_12_files(self):
        from services.workspace.renderers import arc42
        ws = self._make_ws()
        data = self._minimal_data()
        paths = arc42.render_all(ws, data)
        self.assertEqual(len(paths), 12)
        for p in paths:
            self.assertTrue(p.exists(), f"File missing: {p}")

    def test_render_all_idempotent(self):
        from services.workspace.renderers import arc42
        ws = self._make_ws()
        data = self._minimal_data()
        paths1 = arc42.render_all(ws, data)
        paths2 = arc42.render_all(ws, data)
        for p1, p2 in zip(paths1, paths2):
            self.assertEqual(p1.read_text(), p2.read_text())

    def test_introduction_contains_problem_statement(self):
        from services.workspace.renderers.arc42 import render_01_introduction
        ws = self._make_ws()
        data = self._minimal_data()
        p = render_01_introduction(ws, data)
        self.assertIn("We need to test things.", p.read_text())

    def test_section_files_have_correct_numbering(self):
        from services.workspace.renderers import arc42
        ws = self._make_ws()
        data = self._minimal_data()
        paths = arc42.render_all(ws, data)
        for i, p in enumerate(paths, start=1):
            self.assertTrue(p.name.startswith(f"{i:02d}_"), f"Bad name: {p.name}")


# ---------------------------------------------------------------------------
# Per-artifact renderers
# ---------------------------------------------------------------------------

class TestArtifactRenderers(unittest.TestCase):
    def _make_ws(self):
        from services.workspace.workspace import ProjectWorkspace
        tmp = Path(tempfile.mkdtemp())
        ws = ProjectWorkspace(tmp)
        ws.scaffold()
        return ws

    def test_adr_renderer(self):
        from services.workspace.renderers import adr
        ws = self._make_ws()
        dec = MagicMock()
        dec.title = "Use PostgreSQL"
        dec.context = "Need ACID"
        dec.decision = "We will use PG"
        dec.consequences = {"positive": ["reliable"], "negative": ["ops overhead"]}
        dec.created_at = None
        paths = adr.render_all(ws, [dec])
        self.assertEqual(len(paths), 1)
        text = paths[0].read_text()
        self.assertIn("ADR-0001", text)
        self.assertIn("Use PostgreSQL", text)

    def test_story_renderer(self):
        from services.workspace.renderers import stories
        ws = self._make_ws()
        story = MagicMock()
        story.as_a = "developer"
        story.i_want = "tests"
        story.so_that = "I can refactor safely"
        story.priority = "must"
        story.status = "confirmed"
        story.acceptance_criteria = []
        paths = stories.render_all(ws, [story])
        self.assertEqual(len(paths), 1)
        self.assertIn("developer", paths[0].read_text())

    def test_spec_renderer(self):
        from services.workspace.renderers import specs
        ws = self._make_ws()
        spec = MagicMock()
        spec.description = "Login succeeds"
        spec.test_type = "integration"
        spec.given_context = "user exists"
        spec.when_action = "user logs in"
        spec.then_expectation = "token returned"
        paths = specs.render_all(ws, [spec])
        self.assertEqual(len(paths), 1)
        text = paths[0].read_text()
        self.assertIn("SPEC-001", text)
        self.assertIn("integration", text)

    def test_c4_renderer(self):
        from services.workspace.renderers.c4 import render_c4
        ws = self._make_ws()
        comp = MagicMock()
        comp.name = "API Server"
        comp.component_type = "service"
        comp.responsibility = "Handles HTTP requests"
        comp.file_paths = []
        p = render_c4(ws, "MyApp", [comp])
        text = p.read_text()
        self.assertIn("workspace {", text)
        self.assertIn("MyApp", text)
        self.assertIn("API_Server", text)

    def test_readme_renderer(self):
        from services.workspace.renderers.readme import render_readme
        from services.export.queries import Arc42ExportData
        ws = self._make_ws()
        data = Arc42ExportData(
            project_name="My App",
            problem_statement=None,
            constraints=[], components=[], decisions=[],
            stories=[], specs=[], tasks=[],
        )
        p = render_readme(ws, data)
        text = p.read_text()
        self.assertIn("My App", text)
        self.assertIn("arc42", text)
        self.assertIn("tasks.json", text)


if __name__ == "__main__":
    unittest.main()
