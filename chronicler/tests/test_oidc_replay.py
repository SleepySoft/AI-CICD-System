"""OIDC 回调重放容错测试（2026-09-06 实测：模拟插件/刷新重复请求回调）。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from types import SimpleNamespace

from chronicler.app import auth, db
from chronicler.app.config import Cfg


def _fake_transport(status: int, text: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=text)
    return httpx.MockTransport(handler)


def _fake_httpx(transport):
    """只替换 oidc 模块命名空间里的 httpx（保留真实模块供 lambda 内部使用）。"""
    return SimpleNamespace(AsyncClient=lambda *a, **k: httpx.AsyncClient(transport=transport, timeout=10))


class OidcReplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_patch = patch.object(Cfg, "DATA", Path(self.tmp.name) / "private" / "chronicler")
        self.data_patch.start()
        self._backend = patch.object(Cfg, "AUTH_BACKEND", "oidc")
        self._backend.start()
        # 隔离真实 .env（本机已糊化，避免启动迁移读到真实 VAULT: 引用）
        from chronicler.app.vault import sync as _sync
        self._profile = patch.object(_sync, "PROFILE",
                                     SimpleNamespace(install_root=Path(self.tmp.name)))
        self._profile.start()
        db.close()
        db.init()
        db.execute("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,1)",
                   ("bob", auth.hash_password("x"), "user"))

    def tearDown(self):
        db.close()
        self._backend.stop()
        self._profile.stop()
        self.data_patch.stop()
        self.tmp.cleanup()

    def _client(self) -> TestClient:
        with patch("chronicler.app.tasks.start_scheduler"), \
                patch("chronicler.app.tasks.backfill_preset_tasks"):
            from chronicler.app.main import create_app
            return TestClient(create_app("normal"), follow_redirects=False)

    def _valid_state(self) -> str:
        from chronicler.app.routers import oidc
        return oidc._state.dumps({"t": 12345})

    def test_replay_with_valid_session_redirects_home(self):
        """code 已被消费（invalid_grant）但带有效会话 cookie → 视为重放，307 放行。"""
        from chronicler.app.routers import oidc
        bad = _fake_transport(400, '{"error":"invalid_grant","error_description":"Code not valid"}')
        client = self._client()
        client.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("bob"))
        with patch("chronicler.app.routers.oidc.httpx", _fake_httpx(bad)):
            resp = client.get("/api/auth/oidc/callback",
                              params={"code": "spent", "state": self._valid_state()})
        assert resp.status_code == 307 and resp.headers["location"] == "/", resp.text
        client.close()

    def test_spent_code_without_session_rejected(self):
        """code 已被消费且无有效会话 → 401，提示重新登录。"""
        from chronicler.app.routers import oidc
        bad = _fake_transport(400, '{"error":"invalid_grant","error_description":"Code not valid"}')
        client = self._client()
        with patch("chronicler.app.routers.oidc.httpx", _fake_httpx(bad)):
            resp = client.get("/api/auth/oidc/callback",
                              params={"code": "spent", "state": self._valid_state()})
        assert resp.status_code == 401
        assert "重新发起登录" in resp.json()["detail"]
        client.close()

    def test_invalid_state_rejected(self):
        client = self._client()
        resp = client.get("/api/auth/oidc/callback", params={"code": "x", "state": "forged"})
        assert resp.status_code == 400
        client.close()


if __name__ == "__main__":
    unittest.main()
