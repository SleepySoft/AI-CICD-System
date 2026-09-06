"""Web 初始化模块单测（FR-INIT-001/004/005/006/010）。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from chronicler.app.config import Cfg
from chronicler.app.initialization import catalog, config_store, orchestrator, planner, preflight, security, store


class InitializationTest(unittest.TestCase):
    def setUp(self):
        config_store.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.components = self.root / "components"
        self.components.mkdir()
        self.data = self.root / "private" / "chronicler"
        self.data_patch = patch.object(Cfg, "DATA", self.data)
        self.components_patch = patch.object(Cfg, "COMPONENTS_DIR", self.components)
        self.data_patch.start()
        self.components_patch.start()

    def tearDown(self):
        import gc
        import time
        from chronicler.app import db
        db.close()
        config_store.clear()
        self.components_patch.stop()
        self.data_patch.stop()
        gc.collect()
        for _ in range(20):  # Windows：TestClient worker 线程的数据库连接释放有延迟
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.2)

    def component(self, name, *, profiles=None, depends=None, fields=None,
                  dependency_only=False, group="测试组件"):
        path = self.components / name
        path.mkdir()
        (path / "plugin.yaml").write_text(yaml.safe_dump({
            "name": name, "group": group, "desc": f"{name} description",
        }), encoding="utf-8")
        (path / "setup.yaml").write_text(yaml.safe_dump({
            "schema_version": 1,
            "profiles": profiles or [],
            "depends_on": depends or [],
            "dependency_only": dependency_only,
            "conflicts_with": [],
            "platforms": [catalog.current_platform()],
            "fields": fields or [],
            "readiness": {"kind": "container-health", "timeout_sec": 30},
        }), encoding="utf-8")

    def test_catalog_rejects_unmarked_secret(self):
        self.component("bad", fields=[{"key": "API_TOKEN", "kind": "text"}])
        entry = catalog.load()["bad"]
        self.assertIn("kind=secret", entry["error"])

    def test_catalog_requires_secret_semantics(self):
        base = {"key": "APP_SECRET", "kind": "secret", "secret_type": "api-token",
                "generate": "token", "generate_length": 32, "rotation_risk": "low",
                "help": "用于测试的 API 认证令牌。"}
        for missing in ("secret_type", "generate_length", "rotation_risk", "help"):
            field = dict(base)
            del field[missing]
            self.component(f"bad-{missing}", fields=[field])
        entries = catalog.load()
        expected = {"secret_type": "secret_type", "generate_length": "generate_length",
                    "rotation_risk": "rotation_risk", "help": "用途和轮换说明"}
        for missing, message in expected.items():
            self.assertIn(message, entries[f"bad-{missing}"]["error"])

    def test_repository_component_catalog_is_valid(self):
        component_dir = Path(__file__).parents[1] / "components"
        with patch.object(Cfg, "COMPONENTS_DIR", component_dir):
            entries = catalog.load()
        self.assertEqual(15, len(entries))
        self.assertEqual([], [name for name, entry in entries.items() if entry["error"]])

    def test_identity_provider_template_does_not_own_consumers(self):
        realm_path = Path(__file__).parents[1] / "components" / "keycloak" / "realm" / "aisystem-realm.json"
        realm = json.loads(realm_path.read_text(encoding="utf-8"))
        self.assertEqual([], realm["clients"])

    def test_initialization_core_has_no_managed_component_names(self):
        source_dir = Path(__file__).parents[1] / "app" / "initialization"
        managed = ("caddy", "gitea", "jenkins", "keycloak", "mkdocs", "ollama", "openproject",
                   "outline", "postgres", "qdrant", "redis", "sshwifty", "terminal-runtime",
                   "uptime-kuma")
        for path in source_dir.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".js", ".html"}:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for name in managed:
                self.assertNotIn(name, text, f"{path.name} contains component knowledge: {name}")

    def test_plan_adds_dependency_and_is_stable(self):
        self.component("db", profiles=[])
        self.component("app", profiles=["recommended"], depends=["db"])
        first = planner.build("recommended", [], {}, 3)
        second = planner.build("recommended", [], {}, 3)
        self.assertEqual(["db", "app"], [x["name"] for x in first["components"]])
        self.assertEqual("dependency-of:app", first["components"][0]["reason"])
        self.assertEqual(first["plan_hash"], second["plan_hash"])

    def test_dependency_only_component_is_automatic_and_grouped(self):
        self.component("db", dependency_only=True, group="数据存储")
        self.component("app", depends=["db"])
        entries = catalog.load()
        selected, reasons = planner._selected("custom", ["app"], entries)
        self.assertEqual({"app", "db"}, selected)
        self.assertEqual("dependency-of:app", reasons["db"])
        with self.assertRaisesRegex(planner.PlanError, "只能由其他组件"):
            planner._selected("custom", ["db"], entries)
        public = {item["name"]: item for item in catalog.public_catalog()["components"]}
        self.assertTrue(public["db"]["dependency_only"])
        self.assertEqual("数据存储", public["db"]["group"])

    def test_plan_rejects_dependency_cycle(self):
        self.component("a", depends=["b"])
        self.component("b", depends=["a"])
        with self.assertRaisesRegex(planner.PlanError, "依赖存在环"):
            planner.build("custom", ["a"], {}, 1)

    def test_draft_never_stores_secret_value(self):
        store.init_schema()
        result = store.save_draft("config", "custom", [], {"HTTP_PORT": 80}, {"PASSWORD": True})
        raw = self.data.joinpath("chronicler.db").read_bytes()
        self.assertEqual({"PASSWORD": True}, result["secrets"])
        self.assertNotIn(b"actual-secret", raw)

    def test_bootstrap_code_is_one_time_capability(self):
        store.ensure_installation()
        code = security.issue_code()
        token = security.exchange(code)
        self.assertTrue(token)
        with self.assertRaises(Exception):
            security.exchange(code)
        stored = store.installation()
        self.assertNotEqual(code, stored["bootstrap_token_hash"])
        store.execute("UPDATE installation SET bootstrap_closed_at=1 WHERE id=1")
        with self.assertRaises(Exception):
            security.exchange(code)

    def test_public_status_does_not_expose_draft_values(self):
        from fastapi.testclient import TestClient
        from chronicler.app.main import create_app
        store.ensure_installation()
        store.save_draft("config", "custom", [], {"BASE_DOMAIN": "private.example"}, {})
        with TestClient(create_app("bootstrap")) as client:
            response = client.get("/api/setup/status")
        self.assertEqual(200, response.status_code)
        text = json.dumps(response.json())
        self.assertNotIn("private.example", text)

    def test_unlock_save_and_plan_api(self):
        from fastapi.testclient import TestClient
        from chronicler.app.main import create_app
        self.component("core", profiles=["recommended"])
        store.ensure_installation()
        code = security.issue_code()
        with TestClient(create_app("bootstrap")) as client:
            self.assertEqual(401, client.get("/api/setup/draft").status_code)
            self.assertEqual(200, client.post("/api/setup/unlock", json={"code": code}).status_code)
            saved = client.put("/api/setup/draft", json={
                "stage": "plan", "profile": "recommended", "selections": [],
                "values": {"BASE_DOMAIN": "localhost"},
                "secrets": {"INIT_ADMIN_PASSWORD": "safe-pass-123",
                            "CHRONICLER_SECRET": "session-secret-123456789"},
            })
            self.assertEqual(200, saved.status_code)
            self.assertNotIn("safe-pass-123", saved.text)
            planned = client.post("/api/setup/plan")
            self.assertEqual(200, planned.status_code, planned.text)
            self.assertEqual("core", planned.json()["components"][0]["name"])

    def test_credentials_can_only_be_exported_once_after_plan(self):
        from fastapi.testclient import TestClient
        from chronicler.app.main import create_app
        self.component("service", profiles=["custom"], fields=[{
            "key": "SERVICE_ADMIN", "label": "服务管理员", "kind": "text",
            "summary": "account", "required": True, "default": "operator",
        }])
        store.ensure_installation()
        code = security.issue_code()
        with TestClient(create_app("bootstrap")) as client:
            client.post("/api/setup/unlock", json={"code": code})
            saved = client.put("/api/setup/draft", json={
                "stage": "plan", "profile": "custom", "selections": ["service"],
                "values": {"SERVICE_ADMIN": "operator"},
                "secrets": {"INIT_ADMIN_USERNAME": "admin", "INIT_ADMIN_PASSWORD": "safe-pass-123",
                            "CHRONICLER_SECRET": "session-secret-123456789"},
            })
            self.assertEqual(200, saved.status_code)
            planned = client.post("/api/setup/plan")
            self.assertEqual(200, planned.status_code, planned.text)
            exported = client.post("/api/setup/secrets/export")
            self.assertEqual(200, exported.status_code, exported.text)
            self.assertIn("no-store", exported.headers["cache-control"])
            by_key = {item["key"]: item for item in exported.json()["entries"]}
            self.assertEqual("safe-pass-123", by_key["INIT_ADMIN_PASSWORD"]["value"])
            self.assertEqual("s********3", by_key["INIT_ADMIN_PASSWORD"]["display_value"])
            self.assertEqual("admin", by_key["INIT_ADMIN_USERNAME"]["display_value"])
            self.assertEqual("operator", by_key["SERVICE_ADMIN"]["display_value"])
            again = client.post("/api/setup/secrets/export")
            self.assertEqual(409, again.status_code)
            self.assertNotIn("safe-pass-123", again.text)

    def test_configuration_changes_plan_hash(self):
        first = planner.build("chronicler-only", [], {"HTTP_PORT": 80}, 1, {"TOKEN": "secret-value"})
        second = planner.build("chronicler-only", [], {"HTTP_PORT": 8080}, 1, {"TOKEN": "secret-value"})
        self.assertNotEqual(first["plan_hash"], second["plan_hash"])
        self.assertNotIn("secret-value", json.dumps(first))

    def test_component_field_pattern_is_checked_before_plan(self):
        self.component("service", fields=[{
            "key": "SERVICE_USER", "label": "服务账号", "kind": "text", "required": True,
            "pattern": "^(?!admin$)[a-z_]+$", "validation_message": "不能使用保留账号 admin",
        }])
        with self.assertRaisesRegex(planner.PlanError, "不能使用保留账号 admin"):
            planner.build("custom", ["service"], {"SERVICE_USER": "admin"}, 1)

    def test_config_rejects_newline_injection(self):
        with self.assertRaisesRegex(ValueError, "换行"):
            config_store.set_secrets({"SAFE_SECRET": "value\nINJECTED=yes"})

    def test_stale_plan_cannot_execute(self):
        self.component("core", profiles=["recommended"])
        store.ensure_installation()
        draft = store.save_draft("plan", "recommended", [], {}, {})
        plan = planner.build("recommended", [], {}, draft["revision"])
        saved = orchestrator.save_plan(plan)
        store.save_draft("config", "recommended", [], {"HTTP_PORT": 8080}, {})
        with self.assertRaisesRegex(ValueError, "配置已变化"):
            orchestrator.create_run(saved["id"])

    def test_initial_preflight_defers_component_ports(self):
        draft = {"profile": "recommended", "selections": [], "values": {}}
        with patch.object(preflight, "port_checks", return_value=[
            {"name": "端口 2222", "status": "block", "message": "端口不可用"}
        ]) as mocked:
            initial = preflight.run(draft)
            mocked.assert_not_called()
            self.assertTrue(initial["ok"])

            planned = preflight.run(draft, check_ports=True)
            mocked.assert_called_once()
            self.assertFalse(planned["ok"])

    def test_windows_excluded_port_identifies_component_field(self):
        self.component("service", fields=[{
            "key": "SERVICE_PORT", "label": "服务端口", "kind": "port", "default": 2222,
        }])
        draft = {"profile": "custom", "selections": ["service"], "values": {}}
        with patch.object(preflight, "_windows_excluded_tcp_ranges", return_value=[(2180, 2279)]), \
             patch.object(preflight, "_available_port_suggestion", return_value=22222):
            result = preflight.port_checks(draft)
        self.assertEqual("block", result[0]["status"])
        self.assertEqual("SERVICE_PORT", result[0]["field_key"])
        self.assertIn("service · 服务端口", result[0]["name"])
        self.assertIn("2180-2279", result[0]["message"])
        self.assertIn("22222", result[0]["message"])


if __name__ == "__main__":
    unittest.main()
