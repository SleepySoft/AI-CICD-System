"""危险清理入口：鉴权、确认、陈旧预览、并发与路径边界。"""
import gc
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stdout

from fastapi.testclient import TestClient

from chronicler.app import auth, db, maintenance, projects
from chronicler.app.config import Cfg
from chronicler.components.gitea.hooks import repos as gitea_repos


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(Cfg, "DATA", self.root / "private" / "chronicler"),
            patch.object(Cfg, "PUBLIC", self.root / "public"),
            patch.object(Cfg, "WORKSPACE", self.root / "workspace"),
            patch("chronicler.app.vault.sync.PROFILE", SimpleNamespace(install_root=self.root)),
        ]
        for item in self.patches:
            item.start()
        db.close()
        db.init()
        for name, role in (("admin", "admin"), ("dev", "user")):
            db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,1)",
                       (name, auth.hash_password("x"), role))
        db.execute("INSERT INTO projects(id,name,git_url,shadow_repo,created_at)"
                   " VALUES (1,'demo','https://example.test/source.git',"
                   "'http://git.localhost/admin/demo-shadow.git',1)")
        self.shadow = Cfg.PUBLIC / "shadow" / "demo-shadow"
        self.shadow.mkdir(parents=True)
        (self.shadow / "report.md").write_text("generated", encoding="utf-8")
        self.clone = Cfg.repos_dir() / "1"
        self.clone.mkdir(parents=True)
        (self.clone / "source.txt").write_text("clone", encoding="utf-8")
        with patch("chronicler.app.tasks.start_scheduler"), \
                patch("chronicler.app.tasks.backfill_preset_tasks"):
            from chronicler.app.main import create_app
            self.app = create_app("normal")
        self.admin = TestClient(self.app)
        self.admin.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("admin"))
        self.dev = TestClient(self.app)
        self.dev.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("dev"))

    def tearDown(self):
        self.admin.close()
        self.dev.close()
        db.close()
        for item in reversed(self.patches):
            item.stop()
        gc.collect()
        for _ in range(20):
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                gc.collect()
                time.sleep(.1)

    def _post(self, targets, token=None, confirmation="删除 demo"):
        return self.admin.post("/api/maintenance/cleanup/projects/1", json={
            "targets": targets, "token": token or maintenance.preview()["token"],
            "confirmation": confirmation})

    def test_page_and_api_are_admin_only(self):
        self.assertEqual(200, self.admin.get("/maintenance/cleanup").status_code)
        self.assertEqual(404, self.admin.get("/_maintenance.html").status_code)
        for path in ("/maintenance/cleanup", "/api/maintenance/cleanup/preview"):
            self.assertEqual(403, self.dev.get(path).status_code)
        self.assertEqual(403, self.dev.post("/api/maintenance/cleanup/projects/1", json={
            "targets": ["local_shadow"], "token": "", "confirmation": "删除 demo"}).status_code)
        self.assertEqual(401, TestClient(self.app).get("/maintenance/cleanup").status_code)

    def test_confirmation_staleness_and_active_run_block(self):
        old = maintenance.preview()["token"]
        self.assertEqual(422, self._post(["local_shadow"], confirmation="删除").status_code)
        self.assertTrue(self.shadow.exists())
        (self.shadow / "late.md").write_text("new data", encoding="utf-8")
        self.assertEqual(409, self._post(["local_shadow"], token=old).status_code)
        old = maintenance.preview()["token"]
        db.execute("UPDATE projects SET description='changed' WHERE id=1")
        # 描述不属于清理事实；远端地址变更必须导致预览失效。
        db.execute("UPDATE projects SET shadow_repo='http://git.localhost/admin/changed.git' WHERE id=1")
        self.assertEqual(409, self._post(["local_shadow"], token=old).status_code)
        db.execute("INSERT INTO task_runs(project_id,task_type,status,harness,prompt_version)"
                   " VALUES (1,'task','queued','test','')")
        self.assertEqual(409, self._post(["local_shadow"]).status_code)
        self.assertTrue(self.shadow.exists())

    def test_local_cleanup_preserves_source_and_remote_reference(self):
        response = self._post(["local_shadow", "source_clone"])
        self.assertEqual(200, response.status_code, response.text)
        self.assertFalse(self.shadow.exists())
        self.assertFalse(self.clone.exists())
        self.assertEqual("http://git.localhost/admin/demo-shadow.git",
                         db.q1("SELECT shadow_repo FROM projects WHERE id=1")["shadow_repo"])
        self.assertTrue(db.q1("SELECT id FROM audit_log WHERE action='maintenance.cleanup'"))

    def test_remote_failure_keeps_local_data_and_remote_requires_local(self):
        self.assertEqual(422, self._post(["remote_shadow"]).status_code)
        with patch("chronicler.app.component_exec.run_capability", return_value={"ok": False}):
            response = self._post(["remote_shadow", "local_shadow"])
        self.assertEqual(502, response.status_code)
        self.assertTrue(self.shadow.exists())
        self.assertEqual("http://git.localhost/admin/demo-shadow.git",
                         db.q1("SELECT shadow_repo FROM projects WHERE id=1")["shadow_repo"])

    def test_remote_and_local_cleanup_clears_reference(self):
        with patch("chronicler.app.component_exec.run_capability", return_value={"ok": True}) as hook:
            response = self._post(["remote_shadow", "local_shadow"])
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("", db.q1("SELECT shadow_repo FROM projects WHERE id=1")["shadow_repo"])
        self.assertFalse(self.shadow.exists())
        self.assertEqual("repos.py", hook.call_args.args[0])

    def test_orphan_cleanup_and_symlink_guard(self):
        db.execute("INSERT INTO projects(id,name,git_url,created_at)"
                   " VALUES (3,'former','https://example.test/former.git',1)")
        db.execute("DELETE FROM projects WHERE id=3")
        orphan = Cfg.repos_dir() / "3"
        orphan.mkdir(parents=True)
        (orphan / ".git").mkdir()
        response = self.admin.post("/api/maintenance/cleanup/orphans/3", json={
            "token": maintenance.preview()["token"], "confirmation": "删除残留 3"})
        self.assertEqual(200, response.status_code, response.text)
        self.assertFalse(orphan.exists())
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "important").write_text("preserve", encoding="utf-8")
        self.shadow.rename(self.root / "moved-shadow")
        try:
            self.shadow.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("当前 Windows 用户无创建目录符号链接权限")
        response = self._post(["local_shadow"])
        self.assertEqual(409, response.status_code)
        self.assertTrue((outside / "important").exists())


class GiteaRepoCleanupTest(unittest.TestCase):
    def test_delete_requires_exact_managed_shadow_url(self):
        values = {"GITEA_ADMIN_USER": "admin", "GITEA_ADMIN_PASSWORD": "secret",
                  "CHRONICLER_EXPECTED_REPO_URL": "http://evil.test/admin/demo-shadow.git"}
        with patch.dict("os.environ", values), patch("sys.argv", ["repos.py", "delete", "demo-shadow"]), \
                patch.object(gitea_repos.httpx, "Client") as client, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                gitea_repos.main()
        self.assertEqual(2, caught.exception.code)
        client.assert_not_called()

    def test_delete_managed_shadow_calls_only_exact_repository(self):
        values = {"GITEA_ADMIN_USER": "admin", "GITEA_ADMIN_PASSWORD": "secret",
                  "CHRONICLER_EXPECTED_REPO_URL": "http://git.localhost/admin/demo-shadow.git"}
        with patch.dict("os.environ", values), patch("sys.argv", ["repos.py", "delete", "demo-shadow"]), \
                patch.object(gitea_repos.httpx, "Client") as client, redirect_stdout(io.StringIO()):
            client.return_value.__enter__.return_value.delete.return_value.status_code = 204
            with self.assertRaises(SystemExit) as caught:
                gitea_repos.main()
        self.assertEqual(0, caught.exception.code)
        self.assertEqual("http://127.0.0.1/api/v1/repos/admin/demo-shadow",
                         client.return_value.__enter__.return_value.delete.call_args.args[0])
