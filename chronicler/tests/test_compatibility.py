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

    def test_existing_shadow_with_matching_version_but_old_content_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            shadow = Path(temp) / "shadow"
            shutil.copytree(PROFILE.resource_root / "assets" / "shadow-project", shadow)
            subprocess.run(["git", "init", "-b", "main", str(shadow)], check=True,
                           capture_output=True, encoding="utf-8")
            skill = shadow / "SKILL.md"
            old_content = skill.read_text(encoding="utf-8").replace("## 8. 日常维护流程", "## 8. 旧版维护流程")
            skill.write_text(old_content, encoding="utf-8")
            _, gap = compatibility.shadow_version_gap(shadow, "1.0.0", 1)
            self.assertIn("治理内容修订", gap)
            with patch.object(projects, "record"):
                with self.assertRaisesRegex(RuntimeError, "治理内容修订"):
                    projects._ensure_shadow_governance(shadow, {"name": "sample"})
            self.assertEqual(old_content, skill.read_text(encoding="utf-8"))

    def test_existing_shadow_with_matching_version_but_missing_state_field_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            shadow = Path(temp) / "shadow"
            shutil.copytree(PROFILE.resource_root / "assets" / "shadow-project", shadow)
            state = shadow / ".cognitive-state.yaml"
            state.write_text(state.read_text(encoding="utf-8").replace('  commit: ""\n', ''), encoding="utf-8")
            _, gap = compatibility.shadow_version_gap(shadow, "1.0.0", 1)
            self.assertIn("source 必需字段", gap)

    def test_shadow_line_endings_do_not_create_false_content_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            shadow = Path(temp) / "shadow"
            shutil.copytree(PROFILE.resource_root / "assets" / "shadow-project", shadow)
            for path in (shadow / "SKILL.md", *(shadow / "templates").glob("*.md")):
                path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            versions, gap = compatibility.shadow_version_gap(shadow, "1.0.0", 1)
            self.assertEqual("", gap)
            self.assertTrue(versions["governance_revision"])

    def test_existing_legacy_git_repo_without_governance_is_a_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data, public = root / "data", root / "public"
            data.mkdir()
            shadow = public / "shadow" / "sample-shadow"
            shadow.mkdir(parents=True)
            subprocess.run(["git", "init", "-b", "main", str(shadow)], check=True,
                           capture_output=True, encoding="utf-8")
            (shadow / "README.md").write_text("old shadow\n", encoding="utf-8")
            conn = sqlite3.connect(data / "chronicler.db")
            conn.execute("CREATE TABLE projects(name TEXT)")
            conn.execute("INSERT INTO projects(name) VALUES('sample')")
            conn.commit()
            conn.close()
            with patch.object(Cfg, "DATA", data), patch.object(Cfg, "PUBLIC", public), \
                    patch.object(Cfg, "COMPONENTS_DIR", root / "components"):
                result = compatibility.check()
            self.assertFalse(result["ok"])
            self.assertIn("缺少治理资源", result["issues"][0]["message"])
            self.assertEqual("old shadow\n", (shadow / "README.md").read_text(encoding="utf-8"))
            self.assertFalse((shadow / "SKILL.md").exists())

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
