"""本地密码管理 TUI 测试。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app.auth import verify_password
from chronicler.app.config import Cfg
from chronicler.app import db
from chronicler.app.password_tui import PasswordTUI


class PasswordTUITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "chronicler"
        self.patcher = patch.object(Cfg, "DATA", self.data)
        self.patcher.start()
        self.inputs = []
        self.passwords = []
        db.init()

    def tearDown(self):
        db.close()
        self.patcher.stop()
        self.tmp.cleanup()

    def _tui(self, backend="local", runner=None):
        def input_func(prompt=""):
            return self.inputs.pop(0)

        def password_func(prompt=""):
            return self.passwords.pop(0)

        return PasswordTUI(
            input_func=input_func,
            password_func=password_func,
            backend=backend,
            capability_runner=runner,
        )

    def test_create_and_reset_local_admin(self):
        self.inputs.extend(["boss"])
        self.passwords.extend(["safe-pass-123", "safe-pass-123"])
        self._tui()._create_admin()
        user = db.q1("SELECT username, role, password_hash FROM users WHERE username='boss'")
        self.assertEqual("admin", user["role"])

        self.inputs.extend(["boss"])
        self.passwords.extend(["safe-pass-456", "safe-pass-456"])
        self._tui()._reset_local_password()
        user = db.q1("SELECT password_hash FROM users WHERE username='boss'")
        self.assertTrue(verify_password("safe-pass-456", user["password_hash"]))
        self.assertEqual(2, db.q1("SELECT COUNT(*) AS n FROM audit_log")["n"])

    def test_oidc_mode_blocks_non_admin_local_reset(self):
        db.execute("INSERT INTO users(username,password_hash,role,created_at)"
                   " VALUES ('dev','', 'user', 0)")
        self.inputs.extend(["dev"])
        self._tui(backend="oidc")._reset_local_password()
        user = db.q1("SELECT password_hash FROM users WHERE username='dev'")
        self.assertEqual("", user["password_hash"])

    def test_sso_reset_uses_capability_without_password_args(self):
        calls = []

        def runner(script, args, env=None):
            calls.append((script, args, env))
            return {"ok": True}

        self.inputs.extend(["boss"])
        self.passwords.extend(["safe-pass-456", "safe-pass-456"])
        self._tui(runner=runner)._reset_sso_password()
        self.assertEqual(
            [(
                "users.py",
                ["reset-password", "boss", "--password-env",
                 "CHRONICLER_IDENTITY_RESET_PASSWORD", "--permanent"],
                {"CHRONICLER_IDENTITY_RESET_PASSWORD": "safe-pass-456"},
            )],
            calls,
        )
        self.assertEqual(1, db.q1("SELECT COUNT(*) AS n FROM audit_log")["n"])


if __name__ == "__main__":
    unittest.main()
