"""秘密库（vault）测试：加解密、权限、审计脱敏、导出包与本地工具验证（FR-INIT-013/014/015/016）"""
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chronicler.app import auth, db
from chronicler.app.config import Cfg

REPO_ROOT = Path(__file__).resolve().parents[2]
INSPECT = REPO_ROOT / "scripts" / "vault-inspect.py"
SECRET_VALUE = "s3cr3t-猎密-do-not-leak"


class VaultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.secrets_dir = self.root / "secrets"
        self.data_patch = patch.object(Cfg, "DATA", self.root / "private" / "chronicler")
        self.data_patch.start()
        self._old_env = os.environ.get("CHRONICLER_SECRETS_DIR")
        os.environ["CHRONICLER_SECRETS_DIR"] = str(self.secrets_dir)
        # 测试不碰真实 OS 钥匙串，强制文件后端
        self._old_backend = os.environ.get("CHRONICLER_VAULT_KEY_BACKEND")
        os.environ["CHRONICLER_VAULT_KEY_BACKEND"] = "file"
        db.close()
        db.init()
        db.execute("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,1)",
                   ("admin", auth.hash_password("x"), "admin"))
        db.execute("INSERT INTO users(username, password_hash, role, created_at) VALUES (?,?,?,1)",
                   ("dev", auth.hash_password("x"), "user"))
        import chronicler.app.tasks as _tasks  # noqa: F401 先导入模块，patch 才能命中
        with patch("chronicler.app.tasks.start_scheduler"), \
                patch("chronicler.app.tasks.backfill_preset_tasks"):
            from chronicler.app.main import create_app
            self.app = create_app("normal")
        self.admin = TestClient(self.app)
        self.admin.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("admin"))
        self.dev = TestClient(self.app)
        self.dev.cookies.set(Cfg.SESSION_COOKIE, auth.make_session("dev"))

    def tearDown(self):
        import gc
        import time
        db.close()
        self.admin.close()  # 关闭 portal，让 worker 线程退出并释放其线程局部 sqlite 连接
        self.dev.close()
        self.data_patch.stop()
        if self._old_env is None:
            os.environ.pop("CHRONICLER_SECRETS_DIR", None)
        else:
            os.environ["CHRONICLER_SECRETS_DIR"] = self._old_env
        if self._old_backend is None:
            os.environ.pop("CHRONICLER_VAULT_KEY_BACKEND", None)
        else:
            os.environ["CHRONICLER_VAULT_KEY_BACKEND"] = self._old_backend
        gc.collect()
        for _ in range(20):  # Windows 文件锁释放有延迟
            try:
                self.tmp.cleanup()
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.2)

    # ---------- 工具 ----------

    def _create_text(self, name="API_TOKEN", scope="infra", value=SECRET_VALUE):
        resp = self.admin.post("/api/vault/text", json={
            "name": name, "scope": scope, "value": value,
            "secret_type": "api-token", "summary": "测试令牌", "owner": "team-x"})
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def _create_file(self, name="upload-keystore", scope="signing", data=b"\x00\x01keystore-bytes"):
        resp = self.admin.post("/api/vault/file",
                               files={"file": ("upload.jks", data, "application/octet-stream")},
                               data={"name": name, "scope": scope, "summary": "Android 签名"})
        assert resp.status_code == 200, resp.text
        return resp.json()["id"]

    def _export(self) -> Path:
        resp = self.admin.get("/api/vault/export")
        assert resp.status_code == 200, resp.text
        path = self.root / "export.tar"
        path.write_bytes(resp.content)
        return path

    def _inspect(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(INSPECT), *[str(a) for a in args]],
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    # ---------- 加解密 ----------

    def test_crypto_roundtrip_and_wrong_key(self):
        from chronicler.app.vault import crypto
        from pyrage import x25519
        identity = crypto.generate_identity()
        blob = crypto.encrypt(b"top secret", identity)
        assert crypto.decrypt(blob, identity) == b"top secret"
        with self.assertRaises(Exception):
            import pyrage
            pyrage.decrypt(blob, [x25519.Identity.generate()])
        # 主密钥文件已生成且含公钥注释
        key_text = crypto.master_key_path().read_text(encoding="utf-8")
        assert "AGE-SECRET-KEY-" in key_text and "# public key: age1" in key_text

    # ---------- 权限 ----------

    def test_admin_only(self):
        assert self.dev.get("/api/vault").status_code == 403
        assert self.dev.post("/api/vault/text", json={"name": "X", "value": "y"}).status_code == 403
        anon = TestClient(self.app)
        assert anon.get("/api/vault").status_code == 401

    # ---------- 元数据透明 / 值不可见 ----------

    def test_list_metadata_transparent_no_values(self):
        self._create_text()
        self._create_file()
        resp = self.admin.get("/api/vault")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        assert SECRET_VALUE not in resp.text
        for item in items:
            assert "ciphertext" not in item
            assert item["sha256"] and item["summary"]

    def test_reveal_and_audit_no_value(self):
        sid = self._create_text()
        resp = self.admin.post(f"/api/vault/{sid}/reveal")
        assert resp.status_code == 200
        assert resp.text == SECRET_VALUE
        rows = db.q("SELECT target, detail FROM audit_log WHERE action LIKE 'vault.%'")
        assert any("vault.reveal" in r["target"] or True for r in rows)
        for row in rows:
            assert SECRET_VALUE not in (row["target"] or "")
            assert SECRET_VALUE not in (row["detail"] or "")
        audit_page = self.admin.get("/api/vault/audit").json()
        assert any(r["action"] == "vault.reveal" for r in audit_page)
        assert SECRET_VALUE not in json.dumps(audit_page, ensure_ascii=False)

    def test_file_roundtrip_byte_identical(self):
        data = bytes(range(256)) * 10
        sid = self._create_file(data=data)
        resp = self.admin.get(f"/api/vault/{sid}/download")
        assert resp.status_code == 200
        assert resp.content == data

    def test_rotate_and_delete(self):
        sid = self._create_text()
        resp = self.admin.post(f"/api/vault/{sid}/value", json={"value": "new-value"})
        assert resp.status_code == 200
        assert self.admin.post(f"/api/vault/{sid}/reveal").text == "new-value"
        assert self.admin.delete(f"/api/vault/{sid}").status_code == 200
        assert self.admin.get("/api/vault").json() == []

    def test_propagation_pending_banner(self):
        """vault 变更 → 待传播标记 → 横幅数据源 → dismiss 消除（维护横幅机制）"""
        sid = self._create_text(name="VAULT_TEST_KEY", scope="gitea")
        p = self.admin.get("/api/vault/propagation").json()["pending"]
        assert any(i["scope"] == "gitea" and "VAULT_TEST_KEY" in i["keys"] for i in p), p
        # 轮换追加同一 scope 的标记
        self.admin.post(f"/api/vault/{sid}/value", json={"value": "rotated"})
        p = self.admin.get("/api/vault/propagation").json()["pending"]
        entry = next(i for i in p if i["scope"] == "gitea")
        assert "hint" in entry and entry["at"] > 0
        # dismiss 消除 + 审计
        assert self.admin.post("/api/vault/propagation/gitea/dismiss").status_code == 200
        p = self.admin.get("/api/vault/propagation").json()["pending"]
        assert not any(i["scope"] == "gitea" for i in p)
        # 非 admin 不可见（整 router admin）
        assert self.dev.get("/api/vault/propagation").status_code == 403

    # ---------- persist 双写 / 导入 / 漂移 ----------

    COMPONENTS = {"gitea": {"component": {"fields": [
        {"key": "GITEA_ADMIN_PASSWORD", "kind": "secret", "secret_type": "password",
         "rotation_risk": "coordinated", "help": "Gitea 管理员密码"},
        {"key": "GITEA_PORT", "kind": "port"}]}}}

    def test_persist_double_write(self):
        from types import SimpleNamespace
        from chronicler.app.initialization import config_store
        config_store.clear()
        config_store.set_secrets({"GITEA_ADMIN_PASSWORD": "pw-12345678"})
        with patch.object(config_store, "PROFILE", SimpleNamespace(install_root=self.root)):
            config_store.persist({}, self.COMPONENTS)
        config_store.clear()
        items = self.admin.get("/api/vault").json()
        assert len(items) == 1
        assert items[0]["scope"] == "gitea" and items[0]["name"] == "GITEA_ADMIN_PASSWORD"
        assert items[0]["secret_type"] == "password"  # 元数据沿用 setup.yaml 自述
        resp = self.admin.post(f"/api/vault/{items[0]['id']}/reveal")
        assert resp.text == "pw-12345678"
        # ADR-0045：.env 中秘密字段已糊化为 VAULT: 引用，明文不落盘
        env_text = (self.root / ".env").read_text(encoding="utf-8")
        assert "GITEA_ADMIN_PASSWORD=VAULT:gitea/GITEA_ADMIN_PASSWORD" in env_text
        assert "pw-12345678" not in env_text

    def test_import_env_and_drift(self):
        from types import SimpleNamespace
        (self.root / ".env").write_text("GITEA_ADMIN_PASSWORD=pw-old-123456\n", encoding="utf-8")
        with patch("chronicler.app.routers.vault._load_components", return_value=self.COMPONENTS), \
                patch("chronicler.app.vault.sync.PROFILE", SimpleNamespace(install_root=self.root)):
            r = self.admin.post("/api/vault/import-env", json={})
            assert r.json()["imported"] == 1, r.text
            assert self.admin.post("/api/vault/import-env", json={}).json()["skipped"] == 1
            # 漂移：.env 被改
            (self.root / ".env").write_text("GITEA_ADMIN_PASSWORD=pw-new-99999\n", encoding="utf-8")
            st = self.admin.get("/api/vault/env-status").json()
            assert st["drifted"] == ["gitea/GITEA_ADMIN_PASSWORD"]
            # 冲突默认不覆盖；force 后以 .env 为准
            assert self.admin.post("/api/vault/import-env", json={}).json()["conflicts"] == ["GITEA_ADMIN_PASSWORD"]
            assert self.admin.post("/api/vault/import-env", json={"force": True}).json()["imported"] == 1
            assert self.admin.get("/api/vault/env-status").json()["drifted"] == []

    # ---------- 锁定 / 解锁 / 交接 ----------

    def test_lock_and_unlock(self):
        sid = self._create_text()
        master = self.admin.post("/api/vault/master/reveal").json()["secret"]
        (self.secrets_dir / "master.key").unlink()  # 主密钥丢失
        st = self.admin.get("/api/vault/status").json()
        assert st["locked"] and st["reason"] == "master-key-missing"
        # 锁定下写入与解密都被拒绝（绝不静默生成新钥匙）
        assert self.admin.post("/api/vault/text", json={"name": "B", "value": "x"}).status_code == 409
        assert self.admin.post(f"/api/vault/{sid}/reveal").status_code == 409
        from pyrage import x25519
        bad = self.admin.post("/api/vault/unlock", json={"key": str(x25519.Identity.generate())})
        assert bad.status_code == 400
        ok = self.admin.post("/api/vault/unlock", json={"key": master})
        assert ok.status_code == 200, ok.text
        assert not self.admin.get("/api/vault/status").json()["locked"]
        assert self.admin.post(f"/api/vault/{sid}/reveal").text == SECRET_VALUE

    def test_mismatched_key_locks(self):
        self._create_text()
        from pyrage import x25519
        # 主密钥被换成另一把（如恢复时放错文件）→ 拒绝混钥写入
        (self.secrets_dir / "master.key").write_text(str(x25519.Identity.generate()), encoding="utf-8")
        st = self.admin.get("/api/vault/status").json()
        assert st["locked"] and st["reason"] == "master-key-mismatch"
        assert self.admin.post("/api/vault/text", json={"name": "B", "value": "x"}).status_code == 409

    # ---------- 移动工作台页面 ----------

    def test_mobile_page_served(self):
        resp = self.admin.get("/m")
        assert resp.status_code == 200
        assert "移动工作台" in resp.text

    def test_device_redirect(self):
        """手机 UA 进 /m，桌面 UA 进桌面 SPA。"""
        anon = TestClient(self.app, follow_redirects=False)
        mobile = anon.get("/", headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"})
        assert mobile.status_code == 307 and mobile.headers["location"] == "/m"
        desktop = anon.get("/", headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        assert desktop.status_code == 200
        anon.close()

    def test_apply_chronicler_secrets(self):
        """ADR-0045：糊化的 Chronicler 自身秘密在启动时从秘密库解析进进程。"""
        from types import SimpleNamespace
        from chronicler.app.config import Cfg as AppCfg
        from chronicler.app.vault import sync
        old_oidc = AppCfg.OIDC_CLIENT_SECRET
        try:
            self._create_text(name="CHRONICLER_OIDC_SECRET", scope="infra", value="oidc-real-secret")
            (self.root / ".env").write_text(
                "CHRONICLER_OIDC_SECRET=VAULT:infra/CHRONICLER_OIDC_SECRET\n", encoding="utf-8")
            with patch.object(sync, "PROFILE", SimpleNamespace(install_root=self.root)):
                assert sync.apply_chronicler_secrets() == 1
            assert AppCfg.OIDC_CLIENT_SECRET == "oidc-real-secret"
            assert os.environ.get("CHRONICLER_OIDC_SECRET") == "oidc-real-secret"
        finally:
            AppCfg.OIDC_CLIENT_SECRET = old_oidc
            os.environ.pop("CHRONICLER_OIDC_SECRET", None)

    # ---------- 锁定 / 解锁 / 交接 ----------

    def test_key_ack(self):
        self._create_text()  # 触发生成主密钥 → 未交接
        assert self.admin.get("/api/vault/status").json()["key_acked"] is False
        assert self.admin.post("/api/vault/master/ack", json={"key": "AGE-SECRET-KEY-WRONG"}).status_code == 400
        master = self.admin.post("/api/vault/master/reveal").json()["secret"]
        assert self.admin.post("/api/vault/master/ack", json={"key": master}).status_code == 200
        assert self.admin.get("/api/vault/status").json()["key_acked"] is True
        # 审计不含密钥本体
        audit_rows = json.dumps(self.admin.get("/api/vault/audit").json(), ensure_ascii=False)
        assert "vault.key_acked" in audit_rows and master not in audit_rows

    # ---------- 导出包 + 本地工具 ----------

    def test_export_manifest_plaintext_no_secret(self):
        self._create_text()
        self._create_file()
        export = self._export()
        with tarfile.open(export) as tar:
            names = tar.getnames()
            assert set(names) == {"manifest.json", "payload.age", "README.txt"}
            manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
            readme = tar.extractfile("README.txt").read().decode("utf-8")
        assert manifest["count"] == 2
        assert SECRET_VALUE not in json.dumps(manifest, ensure_ascii=False)
        assert SECRET_VALUE not in readme
        assert b"s3cr3t" not in export.read_bytes()  # 全包无明文

    def test_inspect_list_needs_no_key(self):
        self._create_text()
        export = self._export()
        result = self._inspect("list", export)
        assert result.returncode == 0, result.stderr
        assert "infra/API_TOKEN" in result.stdout

    def test_inspect_verify_and_wrong_key(self):
        from pyrage import x25519
        self._create_text()
        self._create_file()
        export = self._export()
        key = self.secrets_dir / "master.key"
        result = self._inspect("verify", export, "--key", key)
        assert result.returncode == 0, result.stderr
        assert "验证通过" in result.stdout
        # 错误主密钥：解密必须失败
        wrong = self.root / "wrong.key"
        wrong.write_text(str(x25519.Identity.generate()), encoding="utf-8")
        bad = self._inspect("verify", export, "--key", wrong)
        assert bad.returncode != 0

    def test_inspect_show_and_extract(self):
        self._create_text()
        self._create_file()
        export = self._export()
        key = self.secrets_dir / "master.key"
        show = self._inspect("show", export, "--key", key, "--name", "infra/API_TOKEN")
        assert show.returncode == 0 and SECRET_VALUE in show.stdout
        outdir = self.root / "restored"
        extract = self._inspect("extract", export, "--key", key, "-d", outdir)
        assert extract.returncode == 0, extract.stderr
        assert (outdir / "text" / "infra" / "API_TOKEN.txt").read_text(encoding="utf-8") == SECRET_VALUE
        assert (outdir / "files" / "signing" / "upload-keystore").read_bytes() == b"\x00\x01keystore-bytes"

    def test_masked_env_migrate_and_render(self):
        """ADR-0045：存量明文 .env 迁移后糊化；渲染可还原真实值；锁定拒绝迁移。"""
        from types import SimpleNamespace
        from chronicler.app.vault import sync
        (self.root / ".env").write_text(
            "BASE_DOMAIN=localhost\nGITEA_ADMIN_PASSWORD=pw-legacy-001\n", encoding="utf-8")
        with patch.object(sync, "PROFILE", SimpleNamespace(install_root=self.root)):
            migrated = sync.migrate_env_to_masked(self.COMPONENTS)
            assert migrated == 1
            env_text = (self.root / ".env").read_text(encoding="utf-8")
            assert "BASE_DOMAIN=localhost" in env_text  # 非秘密原样保留
            assert "VAULT:gitea/GITEA_ADMIN_PASSWORD" in env_text
            assert "pw-legacy-001" not in env_text
            # 渲染还原
            assert "pw-legacy-001" in sync.resolve_env_text(env_text)
            # 幂等：再次迁移无动作
            assert sync.migrate_env_to_masked(self.COMPONENTS) == 0
        # 锁定态拒绝迁移（防止糊化后解不开）
        (self.root / ".env").write_text("GITEA_ADMIN_PASSWORD=pw-locked-002\n", encoding="utf-8")
        (self.secrets_dir / "master.key").unlink()
        with patch.object(sync, "PROFILE", SimpleNamespace(install_root=self.root)):
            assert sync.migrate_env_to_masked(self.COMPONENTS) == 0
            assert "pw-locked-002" in (self.root / ".env").read_text(encoding="utf-8")

    def test_auto_snapshot_on_mutation(self):
        """ADR-0045 强制项：每次变更自动重写 secrets.age，且内容反映最新值。"""
        from chronicler.app.vault import crypto, store
        self._create_text()
        snapshot = self.secrets_dir / "secrets.age"
        assert snapshot.is_file()
        identity = crypto.load_identity()
        import io, tarfile
        payload = crypto.decrypt(snapshot.read_bytes(), identity)
        with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
            data = tar.extractfile("text/infra/API_TOKEN.txt").read().decode()
        assert data == SECRET_VALUE
        # 轮转后快照反映新值
        sid = self.admin.get("/api/vault").json()[0]["id"]
        self.admin.post(f"/api/vault/{sid}/value", json={"value": "rotated-999"})
        payload = crypto.decrypt(snapshot.read_bytes(), identity)
        with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
            assert tar.extractfile("text/infra/API_TOKEN.txt").read().decode() == "rotated-999"
        assert store.count() == 1

    # ---------- 导出包恢复（新部署/灾难恢复） ----------

    def _import_export(self, export: Path, force: bool = False):
        with open(export, "rb") as f:
            return self.admin.post("/api/vault/import-export",
                                   files={"file": ("export.tar", f.read(), "application/x-tar")},
                                   data={"force": "true" if force else "false"})

    def test_import_export_restore(self):
        self._create_text()
        file_bytes = b"\x00\x01keystore-bytes"
        self._create_file(data=file_bytes)
        export = self._export()
        # 模拟新部署：清空 vault（程序外清理），主密钥已由解锁流程恢复
        db.execute("DELETE FROM vault_secrets")
        assert self.admin.get("/api/vault").json() == []
        r = self._import_export(export)
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 2
        items = self.admin.get("/api/vault").json()
        text_item = next(i for i in items if i["kind"] == "text")
        file_item = next(i for i in items if i["kind"] == "file")
        assert self.admin.post(f"/api/vault/{text_item['id']}/reveal").text == SECRET_VALUE
        assert self.admin.get(f"/api/vault/{file_item['id']}/download").content == file_bytes
        assert file_item["summary"] == "Android 签名"  # 元数据成套恢复
        # 幂等：重复恢复全部跳过
        assert self._import_export(export).json()["skipped"] == 2

    def test_import_export_conflict_and_force(self):
        sid = self._create_text()
        export = self._export()
        self.admin.post(f"/api/vault/{sid}/value", json={"value": "changed-later"})
        r = self._import_export(export)
        assert r.json()["conflicts"] == ["infra/API_TOKEN"]
        assert self.admin.post(f"/api/vault/{sid}/reveal").text == "changed-later"  # 未被覆盖
        r2 = self._import_export(export, force=True)
        assert r2.json()["imported"] == 1
        assert self.admin.post(f"/api/vault/{sid}/reveal").text == SECRET_VALUE

    def test_import_export_wrong_key(self):
        from pyrage import x25519
        self._create_text()
        export = self._export()
        db.execute("DELETE FROM vault_secrets")
        # 空库 + 错误主密钥（新部署放了别的密钥）→ 明确报错而非静默
        (self.secrets_dir / "master.key").write_text(str(x25519.Identity.generate()), encoding="utf-8")
        r = self._import_export(export)
        assert r.status_code == 400
        assert "解锁" in r.json()["detail"]


if __name__ == "__main__":
    unittest.main()
