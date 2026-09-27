"""部署配置必须来自本次 env 文件，不能被宿主进程的旧秘密覆盖。"""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chronicler.app import tools


class SecretDeploymentTest(unittest.TestCase):
    def test_compose_scrubs_stale_interpolation_but_keeps_explicit_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "compose.yml").write_text(
                'services:\n  test:\n    image: test\n    environment:\n'
                '      SECRET: ${DATA_KEY:?}\n      PASSWORD: $OLD_PASSWORD\n'
                '      DEFAULT: ${DEFAULT_KEY:-fallback}\n      LITERAL: $$ESCAPED\n'
                '    volumes: ["${DATA_ROOT}/private:/data"]\n', encoding="utf-8")
            client = Mock()
            client.info.return_value = {}
            with patch.dict(os.environ, {"DATA_KEY": "stale-data-key", "OLD_PASSWORD": "stale-password",
                                         "DEFAULT_KEY": "stale-default", "ESCAPED": "preserved",
                                         "DATA_ROOT": "wrong/path"}), \
                 patch.object(tools, "PROFILE", SimpleNamespace(install_root=root)), \
                 patch.object(tools, "_render_env_if_masked", return_value="fresh-env"), \
                 patch.object(tools, "_client", return_value=client), \
                 patch.object(tools, "record") as audit_record, \
                 patch.object(tools.urllib.request, "getproxies", return_value={}):
                args, env, rendered = tools._compose_up_cmd({"name": "test", "_dir": str(root)})
                audit_record.assert_called_once_with("component.environment", "test", source="vault-rendered-env")
            self.assertNotIn("DATA_KEY", env)
            self.assertNotIn("OLD_PASSWORD", env)
            self.assertNotIn("DEFAULT_KEY", env)
            self.assertEqual(env["ESCAPED"], "preserved")
            self.assertEqual(env["DATA_ROOT"], str(root / "data"))
            self.assertEqual(args[args.index("--env-file") + 1], "fresh-env")
            self.assertEqual(rendered, "fresh-env")

    def test_async_deployment_preserves_operator_and_correlation(self):
        import json
        import threading
        from chronicler.app import db
        from chronicler.app.config import Cfg
        from chronicler.app.auditing import scope, record
        finished = threading.Event()
        def worker(tool):
            try:
                record("component.deploy", tool["name"], result="failed", exit_code=1)
            finally:
                db.close()
                finished.set()
        with tempfile.TemporaryDirectory() as temporary, patch.object(Cfg, "DATA", Path(temporary)):
            db.close()
            db.init()
            try:
                with scope(actor="deploy-operator", correlation_id="deploy-audit-test", source="http"), \
                        patch.object(tools, "_deploy_worker", side_effect=worker):
                    tools.start_deploy({"name": "audit-test-component"})
                    self.assertTrue(finished.wait(5))
                row = db.q1("SELECT actor,detail FROM audit_log WHERE action='component.deploy'")
                self.assertEqual(row["actor"], "deploy-operator")
                self.assertEqual(json.loads(row["detail"])["correlation_id"], "deploy-audit-test")
                self.assertEqual(json.loads(row["detail"])["result"], "failed")
            finally:
                tools._deploy_tasks.pop("audit-test-component", None)
                db.close()
