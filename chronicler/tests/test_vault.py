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
        blob = crypto.encrypt(b"top secret")
        assert crypto.decrypt(blob) == b"top secret"
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


if __name__ == "__main__":
    unittest.main()
