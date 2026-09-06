"""组件能力执行器测试（ADR-0027 能力脚本约定）：发现、环境注入、JSON 契约。"""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import component_exec
from chronicler.app.config import Cfg


class ComponentExecTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.components = Path(self.tmp.name) / "components"
        self.components.mkdir()
        self.patch_components = patch.object(Cfg, "COMPONENTS_DIR", self.components)
        self.patch_components.start()

    def tearDown(self):
        self.patch_components.stop()
        self.tmp.cleanup()

    def _add_component(self, name: str, script: str = "echo.py"):
        comp = self.components / name
        (comp / "hooks").mkdir(parents=True)
        (comp / "plugin.yaml").write_text(
            f"name: {name}\ndesc: t\ngroup: 测试\nurl: ''\ncontainer: ''\n", encoding="utf-8")
        (comp / "hooks" / script).write_text(textwrap.dedent("""\
            import json, os, sys
            print(json.dumps({"ok": True, "args": sys.argv[1:],
                              "field": os.environ.get("DEMO_TOKEN", ""),
                              "container": os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "")}))
            """), encoding="utf-8")

    def test_no_provider_returns_none(self):
        assert component_exec.run_capability("nope.py", []) is None

    def test_discovery_and_json_contract(self):
        self._add_component("demo")
        result = component_exec.run_capability("echo.py", ["a", "b"])
        assert result is not None and result["ok"] and result["args"] == ["a", "b"]

    def test_capability_is_generic_over_component_names(self):
        """核心不含组件名：任意提供同名脚本的组件都能被发现。"""
        self._add_component("whatever")
        assert component_exec.find_capability("echo.py") == "whatever"


if __name__ == "__main__":
    unittest.main()
