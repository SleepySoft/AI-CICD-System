"""OIDC 提示页导航配置：覆盖首次注册和存量客户端更新，不连接生产。"""
import importlib.util
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


def load_hook(component, filename):
    path = Path(__file__).resolve().parents[1] / "components" / component / "hooks" / filename
    spec = importlib.util.spec_from_file_location(f"test_{component}_{filename}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OIDCNavigationTest(unittest.TestCase):
    def test_consumers_restore_home_link_for_new_and_existing_clients(self):
        env = {"CHRONICLER_DEPENDENCY_KEYCLOAK_CONTAINER": "test-kc",
               "KEYCLOAK_ADMIN_PASSWORD": "test-only", "OIDC_GITEA_SECRET": "test-only",
               "OIDC_OUTLINE_SECRET": "test-only", "BASE_DOMAIN": "example.test"}
        with patch.dict(os.environ, env):
            for component, fn, transport, prefix in [
                ("gitea", "configure_oidc_client", "kc", "git"),
                ("outline", "apply", "run", "kb"),
            ]:
                hook = load_hook(component, "initialize.py")
                for exists in (False, True):
                    with self.subTest(component=component, exists=exists):
                        calls = []
                        def invoke(args):
                            calls.append(args)
                            if args[0] == "get":
                                return json.dumps([{"id": "existing"}] if exists else [])
                            return ""
                        with patch.object(hook, transport, side_effect=invoke):
                            getattr(hook, fn)()
                        write = next(args for args in calls if args[0] in ("create", "update"))
                        home = f"http://{prefix}.example.test/"
                        self.assertIn(f"baseUrl={home}", write)
                        self.assertIn(f"rootUrl={home}", write)
                        self.assertEqual(write[0], "update" if exists else "create")

    def test_generic_capability_preserves_callback_and_home_on_upsert(self):
        hook = load_hook("keycloak", "oidc.py")
        for existing in ("", "existing"):
            with self.subTest(existing=existing), \
                 patch.object(hook, "_client_uuid", return_value=existing), \
                 patch.object(hook, "_assign_scope"), \
                 patch.object(hook, "_kcadm", return_value=subprocess.CompletedProcess([], 0, "", "")) as call:
                hook._upsert_client("test", "test-only", "https://app.example.test/", "/callback")
                args, kwargs = call.call_args
                if existing:
                    self.assertIn("baseUrl=https://app.example.test/", args)
                    self.assertIn("rootUrl=https://app.example.test/", args)
                    self.assertIn('redirectUris=["https://app.example.test/callback", "https://app.example.test/*"]', args)
                else:
                    payload = json.loads(kwargs["stdin"])
                    self.assertEqual(payload["baseUrl"], "https://app.example.test/")
                    self.assertEqual(payload["rootUrl"], payload["baseUrl"])
                    self.assertIn("https://app.example.test/callback", payload["redirectUris"])
