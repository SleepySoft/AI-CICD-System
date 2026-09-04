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
        from chronicler.app import db
        db.close()
        config_store.clear()
        self.components_patch.stop()
        self.data_patch.stop()
        self.tmp.cleanup()

    def component(self, name, *, profiles=None, depends=None, fields=None):
        path = self.components / name
        path.mkdir()
        (path / "setup.yaml").write_text(yaml.safe_dump({
            "schema_version": 1,
            "profiles": profiles or [],
            "depends_on": depends or [],
            "conflicts_with": [],
            "platforms": [catalog.current_platform()],
            "fields": fields or [],
            "readiness": {"kind": "container-health", "timeout_sec": 30},
        }), encoding="utf-8")

    def test_catalog_rejects_unmarked_secret(self):
        self.component("bad", fields=[{"key": "API_TOKEN", "kind": "text"}])
        entry = catalog.load()["bad"]
        self.assertIn("kind=secret", entry["error"])

    def test_plan_adds_dependency_and_is_stable(self):
        self.component("db", profiles=[])
        self.component("app", profiles=["recommended"], depends=["db"])
        first = planner.build("recommended", [], {}, 3)
        second = planner.build("recommended", [], {}, 3)
        self.assertEqual(["db", "app"], [x["name"] for x in first["components"]])
        self.assertEqual("dependency-of:app", first["components"][0]["reason"])
        self.assertEqual(first["plan_hash"], second["plan_hash"])

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

    def test_configuration_changes_plan_hash(self):
        first = planner.build("chronicler-only", [], {"HTTP_PORT": 80}, 1, {"TOKEN": "secret-value"})
        second = planner.build("chronicler-only", [], {"HTTP_PORT": 8080}, 1, {"TOKEN": "secret-value"})
        self.assertNotEqual(first["plan_hash"], second["plan_hash"])
        self.assertNotIn("secret-value", json.dumps(first))

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


if __name__ == "__main__":
    unittest.main()
