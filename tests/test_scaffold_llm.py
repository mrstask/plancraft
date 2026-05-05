"""Tests for the Scaffolder LLM layer — mocks the OpenAI client."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _tc(name: str, args: dict) -> MagicMock:
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _resp(*tool_calls) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.tool_calls = list(tool_calls)
    return resp


def _config(has_frontend=False):
    from services.scaffold.tech_stack_reader import ScaffoldConfig
    return ScaffoldConfig(
        has_frontend=has_frontend,
        backend="python",
        frontend="node" if has_frontend else None,
        package_slug="testpkg",
    )


def _mock_db():
    db = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    db.execute.return_value = res
    return db


class TestScaffolderLLMDispatch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.impl_dir = self.tmp / "impl"

    async def test_backend_module_written_with_not_implemented(self):
        from services.scaffold.llm import run_scaffolder_llm
        content = (
            "# generated-by: plancraft-scaffolder\n"
            "class OrderService:\n"
            "    def create(self):\n"
            "        raise NotImplementedError('TODO: TASK-001')\n"
        )
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=_resp(_tc("create_backend_module", {
                    "module_name": "order_service",
                    "component_id": "c1",
                    "content": content,
                }))
            )
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config())]

        path = self.impl_dir / "backend" / "src" / "testpkg" / "order_service.py"
        self.assertTrue(path.exists())
        self.assertIn("NotImplementedError", path.read_text())
        self.assertIn("TODO: TASK-001", path.read_text())
        written = [e for e in events if e["type"] == "file_written"]
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["tool"], "create_backend_module")

    async def test_backend_test_written(self):
        from services.scaffold.llm import run_scaffolder_llm
        content = (
            "# generated-by: plancraft-scaffolder\n"
            "import pytest\n"
            "from testpkg.order_service import OrderService\n"
            "def test_create_raises():\n"
            "    with pytest.raises(NotImplementedError):\n"
            "        OrderService().create()\n"
        )
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=_resp(_tc("create_backend_test", {
                    "test_file_name": "test_order_service",
                    "spec_id": "s1",
                    "content": content,
                }))
            )
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config())]

        path = self.impl_dir / "backend" / "tests" / "test_order_service.py"
        self.assertTrue(path.exists())
        self.assertIn("pytest.raises(NotImplementedError)", path.read_text())

    async def test_frontend_module_written(self):
        from services.scaffold.llm import run_scaffolder_llm
        content = (
            "// generated-by: plancraft-scaffolder\n"
            "export function getOrder(id: string): never {\n"
            "  throw new Error('TODO: TASK-002');\n"
            "}\n"
        )
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=_resp(_tc("create_frontend_module", {
                    "module_name": "OrderService",
                    "component_id": "c2",
                    "content": content,
                }))
            )
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config(has_frontend=True))]

        path = self.impl_dir / "frontend" / "src" / "OrderService.tsx"
        self.assertTrue(path.exists())
        self.assertIn("throw new Error", path.read_text())
        self.assertIn("TODO: TASK-002", path.read_text())

    async def test_frontend_test_written(self):
        from services.scaffold.llm import run_scaffolder_llm
        content = (
            "// generated-by: plancraft-scaffolder\n"
            "import { describe, it, expect } from 'vitest';\n"
            "import { getOrder } from '../src/OrderService';\n"
            "describe('OrderService', () => {\n"
            "  it('throws', () => {\n"
            "    expect(() => getOrder('1')).toThrow();\n"
            "  });\n"
            "});\n"
        )
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=_resp(_tc("create_frontend_test", {
                    "test_file_name": "OrderService",
                    "spec_id": "s2",
                    "content": content,
                }))
            )
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config(has_frontend=True))]

        path = self.impl_dir / "frontend" / "tests" / "OrderService.test.tsx"
        self.assertTrue(path.exists())
        self.assertIn("toThrow", path.read_text())

    async def test_no_tool_calls_emits_progress_not_file_written(self):
        from services.scaffold.llm import run_scaffolder_llm
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.tool_calls = None
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=resp)
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config())]
        self.assertFalse(any(e["type"] == "file_written" for e in events))
        self.assertTrue(any(e["type"] == "scaffold_progress" for e in events))

    async def test_multiple_tool_calls_all_dispatched(self):
        from services.scaffold.llm import run_scaffolder_llm
        tcs = [
            _tc("create_backend_module", {"module_name": "auth", "component_id": "c1",
                                          "content": "# generated-by: plancraft-scaffolder\nclass Auth: pass\n"}),
            _tc("create_backend_module", {"module_name": "billing", "component_id": "c2",
                                          "content": "# generated-by: plancraft-scaffolder\nclass Billing: pass\n"}),
            _tc("create_backend_test", {"test_file_name": "test_auth", "spec_id": "s1",
                                        "content": "# generated-by: plancraft-scaffolder\ndef test_auth(): pass\n"}),
        ]
        with patch("services.scaffold.llm._client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=_resp(*tcs))
            events = [e async for e in run_scaffolder_llm("p1", _mock_db(), self.impl_dir, _config())]

        written = [e for e in events if e["type"] == "file_written"]
        self.assertEqual(len(written), 3)


class TestTechStackReader(unittest.IsolatedAsyncioTestCase):
    def _entry(self, layer, choice):
        e = MagicMock()
        e.layer = layer
        e.choice = choice
        return e

    def _db(self, entries):
        db = AsyncMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = entries
        db.execute.return_value = res
        return db

    async def test_no_frontend_keyword_returns_backend_only(self):
        from services.scaffold.tech_stack_reader import read_scaffold_config
        cfg = await read_scaffold_config("p", self._db([
            self._entry("backend", "FastAPI"),
            self._entry("storage", "PostgreSQL"),
        ]), package_slug="app")
        self.assertFalse(cfg.has_frontend)
        self.assertIsNone(cfg.frontend)

    async def test_react_triggers_frontend(self):
        from services.scaffold.tech_stack_reader import read_scaffold_config
        cfg = await read_scaffold_config("p", self._db([
            self._entry("frontend", "React + Vite"),
        ]), package_slug="app")
        self.assertTrue(cfg.has_frontend)
        self.assertEqual(cfg.frontend, "node")

    async def test_frontend_layer_name_triggers_frontend(self):
        from services.scaffold.tech_stack_reader import read_scaffold_config
        cfg = await read_scaffold_config("p", self._db([
            self._entry("frontend", "Angular"),
        ]), package_slug="app")
        self.assertTrue(cfg.has_frontend)

    async def test_vue_keyword_triggers_frontend(self):
        from services.scaffold.tech_stack_reader import read_scaffold_config
        cfg = await read_scaffold_config("p", self._db([
            self._entry("ui", "Vue 3"),
        ]), package_slug="app")
        self.assertTrue(cfg.has_frontend)

    async def test_package_slug_preserved(self):
        from services.scaffold.tech_stack_reader import read_scaffold_config
        cfg = await read_scaffold_config("p", self._db([]), package_slug="my_project")
        self.assertEqual(cfg.package_slug, "my_project")


if __name__ == "__main__":
    unittest.main()
