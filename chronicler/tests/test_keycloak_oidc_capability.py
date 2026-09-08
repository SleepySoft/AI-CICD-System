"""keycloak 组件 oidc.py 能力的 CLI 契约测试（ADR-0047；不依赖 docker/keycloak）。"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "components" / "keycloak" / "hooks" / "oidc.py"


class KeycloakOidcCapabilityTest(unittest.TestCase):
    def _run(self, *args, env_extra=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("KEYCLOAK_")}
        env.update(env_extra or {})
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=30)

    def test_usage_error(self):
        proc = self._run()
        assert proc.returncode == 2
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["ok"] is False and "upsert-client" in payload["error"]

    def test_missing_admin_password_rejected_before_login(self):
        proc = self._run("upsert-client", "demo", "s3cret", "http://app.localhost", "/cb")
        assert proc.returncode == 2
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["ok"] is False and "KEYCLOAK_ADMIN_PASSWORD" in payload["error"]


if __name__ == "__main__":
    unittest.main()
