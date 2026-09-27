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
                 patch.object(tools.urllib.request, "getproxies", return_value={}):
                args, env, rendered = tools._compose_up_cmd({"name": "test", "_dir": str(root)})
            self.assertNotIn("DATA_KEY", env)
            self.assertNotIn("OLD_PASSWORD", env)
            self.assertNotIn("DEFAULT_KEY", env)
            self.assertEqual(env["ESCAPED"], "preserved")
            self.assertEqual(env["DATA_ROOT"], str(root / "data"))
            self.assertEqual(args[args.index("--env-file") + 1], "fresh-env")
            self.assertEqual(rendered, "fresh-env")
