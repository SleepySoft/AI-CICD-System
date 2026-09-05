"""全量导出（ADR-0041/0042）：外层 tar = 明文 manifest.json + 密文 payload.age + README。

导出物设计目标（资源透明、丢了可发现）：
- manifest.json 明文：有什么秘密、属于哪个 scope、属主、过期时间、明文 sha256——无需密钥即可浏览；
- payload.age 为标准 age 密文：内含全部秘密值，凭主密钥可离线解密（age -d 或 scripts/vault-inspect.py）；
- 每条秘密带明文 sha256：解密后可逐条校验完整性。
"""
import hashlib
import io
import json
import tarfile
import time

from . import crypto, store

FORMAT = "chronicler-vault-export"

README = """Chronicler 秘密库导出包
========================

manifest.json : 明文清单（名称/作用域/属主/过期时间/明文 sha256），无需密钥即可浏览。
payload.age   : 全部秘密值的 age 加密 tar，只有主密钥能解开：
                  age -d -i master.key payload.age > payload.tar
                或使用配套工具：
                  python scripts/vault-inspect.py list    <本文件>            # 无需密钥
                  python scripts/vault-inspect.py verify  <本文件> --key master.key
                  python scripts/vault-inspect.py extract <本文件> --key master.key -d <目录>

内部结构：text/<scope>/<name>.txt 为文本秘密；files/<scope>/<name> 为秘密文件。
主密钥（AGE-SECRET-KEY-...）永不在本包内；请另行保管。
"""


def _arcname(row: dict) -> str:
    if row["kind"] == "text":
        return f"text/{row['scope']}/{row['name']}.txt"
    return f"files/{row['scope']}/{row['name']}"


def _add(tar: tarfile.TarFile, arcname: str, data: bytes, mtime: float, mode: int):
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    info.mtime = int(mtime)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def build_export() -> tuple[bytes, int]:
    """打包全部秘密；返回 (tar 字节, 秘密条数)。"""
    rows = store.all_rows()
    payload_buf = io.BytesIO()
    items = []
    with tarfile.open(fileobj=payload_buf, mode="w") as tar:
        for row in rows:
            plain = crypto.decrypt(row["ciphertext"])
            _add(tar, _arcname(row), plain, row["updated_at"], 0o600)
            items.append({
                "name": row["name"], "scope": row["scope"], "kind": row["kind"],
                "secret_type": row["secret_type"], "rotation_risk": row["rotation_risk"],
                "summary": row["summary"], "owner": row["owner"],
                "expires_at": row["expires_at"], "filename": row["filename"],
                "path": _arcname(row), "size": len(plain),
                "sha256": hashlib.sha256(plain).hexdigest(),
            })
    encrypted = crypto.encrypt(payload_buf.getvalue())
    manifest = {
        "format": FORMAT,
        "version": 1,
        "exported_at": time.time(),
        "recipient": crypto.recipient_str(),
        "count": len(items),
        "payload_sha256": hashlib.sha256(encrypted).hexdigest(),
        "items": items,
    }
    now = time.time()
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        _add(tar, "manifest.json",
             json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"), now, 0o644)
        _add(tar, "payload.age", encrypted, now, 0o644)
        _add(tar, "README.txt", README.encode("utf-8"), now, 0o644)
    return out.getvalue(), len(items)
