import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import compatibility, projects
from chronicler.app.config import Cfg
from chronicler.app.runtime import PROFILE


class CompatibilityCheckTest(unittest.TestCase):
    def test_component_contract_gap_is_reported_without_changing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            component = root / "components" / "sample"
            component.mkdir(parents=True)
            (component / "plugin.yaml").write_text("name: sample\n", encoding="utf-8")
            setup = component / "setup.yaml"
            setup.write_text("schema_version: 2\n", encoding="utf-8")
            with patch.object(Cfg, "COMPONENTS_DIR", root / "components"), \
                    patch.object(Cfg, "DATA", root / "data"):
                components, issues = compatibility._component_checks()
            self.assertEqual("gap", components[0]["status"])
            self.assertEqual("contract_invalid", issues[0]["code"])
            self.assertEqual("schema_version: 2\n", setup.read_text(encoding="utf-8"))

    def test_component_revision_changes_with_deployment_definition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            component = root / "components" / "sample"
            component.mkdir(parents=True)
            (component / "plugin.yaml").write_text("name: sample\n", encoding="utf-8")
            (component / "setup.yaml").write_text("schema_version: 1\n", encoding="utf-8")
            compose = component / "compose.yml"
            compose.write_text("services: {}\n", encoding="utf-8")
            with patch.object(Cfg, "COMPONENTS_DIR", root / "components"), \
                    patch.object(Cfg, "DATA", root / "data"):
                first, _ = compatibility._component_checks()
                compose.write_text("services:\n  app: {}\n", encoding="utf-8")
                second, _ = compatibility._component_checks()
            self.assertNotEqual(first[0]["definition_revision"], second[0]["definition_revision"])
            self.assertEqual("definition-valid/runtime-unverified", second[0]["status"])

    def test_shadow_version_gap_is_reported_and_blocks_task_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, public = root / "data", root / "public"
            data.mkdir()
            shadow = public / "shadow" / "sample-shadow"
            shutil.copytree(PROFILE.resource_root / "assets" / "shadow-project", shadow)
            subprocess.run(["git", "init", "-b", "main", str(shadow)], check=True,
                           capture_output=True, encoding="utf-8")
            state = shadow / ".cognitive-state.yaml"
            original = state.read_text(encoding="utf-8")
            state.write_text(original.replace("skill_version: 1.0.0", "skill_version: 0.9.0"), encoding="utf-8")
            conn = sqlite3.connect(data / "chronicler.db")
            conn.execute("CREATE TABLE projects(name TEXT)")
            conn.execute("INSERT INTO projects(name) VALUES('sample')")
            conn.commit()
            conn.close()
            with patch.object(Cfg, "DATA", data), patch.object(Cfg, "PUBLIC", public), \
                    patch.object(Cfg, "COMPONENTS_DIR", root / "components"):
                result = compatibility.check()
                self.assertFalse(result["ok"])
                self.assertEqual("shadow_contract_gap", result["issues"][0]["code"])
                self.assertEqual("gap", result["workspaces"][0]["status"])
                with patch.object(projects, "record"):
                    with self.assertRaisesRegex(RuntimeError, "版本检查失败"):
                        projects._ensure_shadow_governance(shadow, {"name": "sample"})
            self.assertEqual(original.replace("skill_version: 1.0.0", "skill_version: 0.9.0"),
                             state.read_text(encoding="utf-8"))

    def test_uninitialized_shadow_is_reported_without_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            conn = sqlite3.connect(data / "chronicler.db")
            conn.execute("CREATE TABLE projects(name TEXT)")
            conn.execute("INSERT INTO projects(name) VALUES('sample')")
            conn.commit()
            conn.close()
            with patch.object(Cfg, "DATA", data), patch.object(Cfg, "PUBLIC", root / "public"), \
                    patch.object(Cfg, "COMPONENTS_DIR", root / "components"):
                result = compatibility.check()
            self.assertTrue(result["ok"])
            self.assertEqual("uninitialized", result["workspaces"][0]["status"])
            self.assertFalse((root / "public").exists())


if __name__ == "__main__":
    unittest.main()
