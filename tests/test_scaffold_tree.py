"""Tests for the deterministic scaffold tree builder and rubric."""
import json
import stat
import tempfile
import unittest
from pathlib import Path


def _make_config(has_frontend=False, pkg="myapp"):
    from services.scaffold.tech_stack_reader import ScaffoldConfig
    return ScaffoldConfig(
        has_frontend=has_frontend,
        backend="python",
        frontend="node" if has_frontend else None,
        package_slug=pkg,
    )


class TestBackendOnlyTree(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.impl_dir = self.tmp / "impl"

    def test_creates_backend_dirs(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        self.assertTrue((self.impl_dir / "backend" / "src" / "myapp").is_dir())
        self.assertTrue((self.impl_dir / "backend" / "tests").is_dir())

    def test_no_frontend_dir_without_frontend(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        self.assertFalse((self.impl_dir / "frontend").exists())

    def test_required_files_written(self):
        from services.scaffold.tree_builder import build_static_tree, SCAFFOLD_MARKER
        written = build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        names = {p.name for p in written}
        for expected in [
            "bootstrap.sh", ".gitignore", ".env.template", "README.md",
            "requirements.txt", "pyproject.toml", "__init__.py", "main.py",
            "conftest.py", SCAFFOLD_MARKER,
        ]:
            self.assertIn(expected, names, f"Missing: {expected}")

    def test_marker_metadata(self):
        from services.scaffold.tree_builder import build_static_tree, SCAFFOLD_MARKER
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        marker = json.loads((self.impl_dir / SCAFFOLD_MARKER).read_text())
        self.assertEqual(marker["generator"], "plancraft-scaffolder")
        self.assertFalse(marker["has_frontend"])
        self.assertEqual(marker["package_slug"], "myapp")
        self.assertIn("generated_at", marker)

    def test_bootstrap_is_executable(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        mode = (self.impl_dir / "bootstrap.sh").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_main_py_has_fastapi_app(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        content = (self.impl_dir / "backend" / "src" / "myapp" / "main.py").read_text()
        self.assertIn("FastAPI", content)
        self.assertIn("app = FastAPI", content)

    def test_requirements_has_fastapi(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        content = (self.impl_dir / "backend" / "requirements.txt").read_text()
        self.assertIn("fastapi", content)
        self.assertIn("pytest", content)

    def test_conftest_imports_app(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(), "My App", force=True)
        content = (self.impl_dir / "backend" / "tests" / "conftest.py").read_text()
        self.assertIn("from myapp.main import app", content)


class TestFrontendTree(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.impl_dir = self.tmp / "impl"

    def test_frontend_dirs_exist(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(has_frontend=True), "Web App", force=True)
        self.assertTrue((self.impl_dir / "frontend" / "src").is_dir())
        self.assertTrue((self.impl_dir / "frontend" / "tests").is_dir())

    def test_frontend_files_written(self):
        from services.scaffold.tree_builder import build_static_tree
        written = build_static_tree(self.impl_dir, _make_config(has_frontend=True), "Web App", force=True)
        names = {p.name for p in written}
        for expected in ["package.json", "tsconfig.json", "vite.config.ts", "index.html", "main.tsx"]:
            self.assertIn(expected, names, f"Missing: {expected}")

    def test_package_json_has_vitest(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(has_frontend=True), "Web App", force=True)
        pkg = json.loads((self.impl_dir / "frontend" / "package.json").read_text())
        self.assertIn("vitest", pkg["devDependencies"])
        self.assertIn("react", pkg["dependencies"])

    def test_bootstrap_includes_npm_install(self):
        from services.scaffold.tree_builder import build_static_tree
        build_static_tree(self.impl_dir, _make_config(has_frontend=True), "Web App", force=True)
        bootstrap = (self.impl_dir / "bootstrap.sh").read_text()
        self.assertIn("npm install", bootstrap)

    def test_marker_records_has_frontend_true(self):
        from services.scaffold.tree_builder import build_static_tree, SCAFFOLD_MARKER
        build_static_tree(self.impl_dir, _make_config(has_frontend=True), "Web App", force=True)
        marker = json.loads((self.impl_dir / SCAFFOLD_MARKER).read_text())
        self.assertTrue(marker["has_frontend"])


class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.impl_dir = self.tmp / "impl"

    def test_human_edited_file_not_overwritten(self):
        from services.scaffold.tree_builder import build_static_tree
        cfg = _make_config(pkg="proj")
        build_static_tree(self.impl_dir, cfg, "Proj", force=False)

        main_py = self.impl_dir / "backend" / "src" / "proj" / "main.py"
        main_py.write_text("# human edit\nprint('custom')\n", encoding="utf-8")

        build_static_tree(self.impl_dir, cfg, "Proj", force=False)

        content = main_py.read_text()
        self.assertIn("human edit", content)
        self.assertNotIn("FastAPI", content)

    def test_force_overwrites_generated_files(self):
        from services.scaffold.tree_builder import build_static_tree
        cfg = _make_config(pkg="proj")
        build_static_tree(self.impl_dir, cfg, "Proj", force=True)

        main_py = self.impl_dir / "backend" / "src" / "proj" / "main.py"
        main_py.write_text(
            "# generated-by: plancraft-scaffolder\n# old generated\n",
            encoding="utf-8",
        )

        build_static_tree(self.impl_dir, cfg, "Proj", force=True)
        self.assertIn("FastAPI", main_py.read_text())

    def test_second_run_without_force_is_safe(self):
        from services.scaffold.tree_builder import build_static_tree, SCAFFOLD_MARKER
        cfg = _make_config(pkg="proj")
        build_static_tree(self.impl_dir, cfg, "Proj", force=True)
        # second run must not raise
        build_static_tree(self.impl_dir, cfg, "Proj", force=False)
        self.assertTrue((self.impl_dir / SCAFFOLD_MARKER).exists())


class TestRubric(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.impl_dir = self.tmp / "impl"
        self.pkg = "rubricpkg"
        src = self.impl_dir / "backend" / "src" / self.pkg
        src.mkdir(parents=True)
        (self.impl_dir / "backend" / "tests").mkdir(parents=True)
        self.src = src

    def test_passes_when_all_criteria_met(self):
        from services.scaffold.rubric import ScaffoldRubric
        (self.src / "user_service.py").write_text(
            "# generated-by: plancraft-scaffolder\n"
            "class UserService:\n"
            "    def get(self, uid: str) -> None:\n"
            "        raise NotImplementedError('TODO: TASK-001')\n",
        )
        (self.impl_dir / "backend" / "tests" / "test_user_service.py").write_text(
            "# generated-by: plancraft-scaffolder\n"
            "import pytest\n"
            "from rubricpkg.user_service import UserService\n"
            "def test_get_raises():\n"
            "    with pytest.raises(NotImplementedError):\n"
            "        UserService().get('x')\n",
        )
        result = ScaffoldRubric().check(
            self.impl_dir, self.pkg,
            component_names=["User Service"], spec_count=1, has_frontend=False,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)

    def test_fails_when_no_module_for_component(self):
        from services.scaffold.rubric import ScaffoldRubric
        result = ScaffoldRubric().check(
            self.impl_dir, self.pkg,
            component_names=["Payment Gateway"], spec_count=0, has_frontend=False,
        )
        self.assertFalse(result.passed)
        self.assertIn("Payment Gateway", result.missing_component_modules)

    def test_fails_when_specs_exist_but_no_test_files(self):
        from services.scaffold.rubric import ScaffoldRubric
        (self.src / "auth.py").write_text("# generated-by: plancraft-scaffolder\n")
        result = ScaffoldRubric().check(
            self.impl_dir, self.pkg,
            component_names=["Auth"], spec_count=2, has_frontend=False,
        )
        self.assertFalse(result.passed)
        self.assertTrue(result.missing_test_files)

    def test_score_decreases_with_issues(self):
        from services.scaffold.rubric import ScaffoldRubric
        result = ScaffoldRubric().check(
            self.impl_dir, self.pkg,
            component_names=["A", "B", "C"], spec_count=0, has_frontend=False,
        )
        self.assertLess(result.score, 1.0)


if __name__ == "__main__":
    unittest.main()
