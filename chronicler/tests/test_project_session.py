"""工程常驻会话端点测试（ADR-0046 P1）：打开/状态/上下文注入/权限。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chronicler.app import auth, db
from chronicler.app.config import Cfg


class ProjectSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data_patch = patch.object(Cfg, "DATA", self.root / "private" / "chronicler")
        self.ws_patch = patch.object(Cfg, "WORKSPACE", self.root / "workspace")
        self.data_patch.start()
        self.ws_patch.start()
        # 隔离真实 .env（本机已糊化，避免启动迁移读到真实 VAULT: 引用）
        from types import SimpleNamespace
        from chronicler.app.vault import sync as _sync
        self._profile = patch.object(_sync, "PROFILE",
                                     SimpleNamespace(install_root=self.root))
        self._profile.start()
        db.close()
        db.init()
        db.execute("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,1)",
                   ("admin", auth.hash_password("x"), "admin"))
        db.execute("INSERT INTO projects(id, name, git_url, created_at) VALUES (1,'demo','http://g/x.git',1)")
        (self.root / "workspace" / "repos" / "1").mkdir(parents=True)
        with patch("chronicler.app.tasks.start_scheduler"), \
                patch("chronicler.app.tasks.backfill_preset_tasks"):
            from chronicler.app.main import create_app
            self.app = create_app("normal")
        self.admin = TestClient(self.app)
        self.admin.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("admin"))
        self.other = TestClient(self.app)
        self.other.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("bob"))  # 未建档普通用户
        db.execute("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,1)",
                   ("bob", auth.hash_password("x"), "user"))

    def tearDown(self):
        import gc
        import time
        self.admin.close()
        self.other.close()
        db.close()
        self.ws_patch.stop()
        self._profile.stop()
        self.data_patch.stop()
        gc.collect()
        for _ in range(20):
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.2)

    def test_open_session_injects_context_and_returns_chat_url(self):
        calls = {}
        with patch("chronicler.app.atr.ensure_session", return_value=True), \
                patch("chronicler.app.atr.send_text",
                      lambda sid, text: calls.setdefault("sent", (sid, text))), \
                patch("chronicler.app.atr._public_base", return_value="http://term.localhost"), \
                patch("chronicler.app.atr._token", return_value="tok123"):
            resp = self.admin.post("/api/projects/1/session/open")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"] == "atr-proj-1" and body["created"] is True
        assert "session=atr-proj-1" in body["chat_url"] and "token=tok123" in body["chat_url"]
        # 上下文注入：会话里展示 + 落 ATR_CONTEXT.md
        assert calls["sent"][0] == "atr-proj-1"
        ctx = (self.root / "workspace" / "repos" / "1" / "ATR_CONTEXT.md").read_text(encoding="utf-8")
        assert "demo" in ctx and "http://g/x.git" in ctx and "禁止" in ctx

    def test_existing_session_not_reinjected(self):
        with patch("chronicler.app.atr.ensure_session", return_value=False), \
                patch("chronicler.app.atr._public_base", return_value="http://term.localhost"), \
                patch("chronicler.app.atr._token", return_value=""):
            resp = self.admin.post("/api/projects/1/session/open")
        assert resp.json()["created"] is False

    def test_session_requires_admin(self):
        with patch("chronicler.app.atr.session_exists", return_value=False):
            assert self.other.post("/api/projects/1/session/open").status_code == 403
            assert self.other.get("/api/projects/1/session").status_code == 200  # 状态查询全员可读


if __name__ == "__main__":
    unittest.main()
