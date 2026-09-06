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


def build_payload() -> tuple[bytes, list, "object"]:
    """打包全部秘密为 payload tar；返回 (tar 字节, 条目清单, 主密钥身份)。锁定时抛 VaultLocked。"""
    rows = store.all_rows()
    identity = store._identity_verified()
    payload_buf = io.BytesIO()
    items = []
    with tarfile.open(fileobj=payload_buf, mode="w") as tar:
        for row in rows:
            plain = crypto.decrypt(row["ciphertext"], identity)
            _add(tar, _arcname(row), plain, row["updated_at"], 0o600)
            items.append({
                "name": row["name"], "scope": row["scope"], "kind": row["kind"],
                "secret_type": row["secret_type"], "rotation_risk": row["rotation_risk"],
                "summary": row["summary"], "owner": row["owner"],
                "expires_at": row["expires_at"], "filename": row["filename"],
                "path": _arcname(row), "size": len(plain),
                "sha256": hashlib.sha256(plain).hexdigest(),
            })
    return payload_buf.getvalue(), items, identity


def write_snapshot():
    """自动快照（ADR-0045 强制项）：每次变更后重写 secrets/secrets.age（密文，可入库）。"""
    import os
    payload, _, identity = build_payload()
    blob = crypto.encrypt(payload, identity)
    path = crypto.secrets_dir() / "secrets.age"
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def build_export() -> tuple[bytes, int]:
    """打包全部秘密；返回 (tar 字节, 秘密条数)。"""
    payload, items, identity = build_payload()
    encrypted = crypto.encrypt(payload, identity)
    manifest = {
        "format": FORMAT,
        "version": 1,
        "exported_at": time.time(),
        "recipient": crypto.recipient_str(identity),
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


def restore_export(blob: bytes, actor: str, force: bool = False) -> dict:
    """从导出包恢复进 vault（新部署/灾难恢复）。

    流程：校验 payload 摘要 → 主密钥解密 → 逐条校验明文 sha256 → upsert。
    冲突（同名不同值）默认不覆盖，报告由 admin 确认后 force 重试。
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
            payload = tar.extractfile("payload.age").read()
    except (KeyError, tarfile.TarError, json.JSONDecodeError) as e:
        raise ValueError(f"不是有效的导出包：{e}")
    if manifest.get("format") != FORMAT:
        raise ValueError("不是 Chronicler 秘密库导出包（format 不匹配）")
    if hashlib.sha256(payload).hexdigest() != manifest.get("payload_sha256"):
        raise ValueError("payload.age 与清单摘要不一致：导出包可能已被篡改")
    identity = crypto.load_identity()
    try:
        plain_tar = crypto.decrypt(payload, identity)
    except Exception:
        raise ValueError("无法用当前主密钥解密：请先通过「解锁」恢复导出包对应的主密钥"
                         f"（本包接收者：{manifest.get('recipient', '?')}）")
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(plain_tar)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                entries[member.name] = tar.extractfile(member).read()
    imported, skipped, conflicts, corrupted = 0, 0, [], []
    for item in manifest.get("items", []):
        data = entries.get(item["path"])
        if data is None or hashlib.sha256(data).hexdigest() != item["sha256"]:
            corrupted.append(item["path"])
            continue
        existing = store.find(item["scope"], item["name"])
        if existing and existing["sha256"] == item["sha256"]:
            skipped += 1
            continue
        if existing and not force:
            conflicts.append(f"{item['scope']}/{item['name']}")
            continue
        store.upsert(kind=item["kind"], name=item["name"], scope=item["scope"], plain=data,
                     actor=actor, secret_type=item["secret_type"],
                     rotation_risk=item["rotation_risk"], summary=item.get("summary", ""),
                     owner=item.get("owner", ""), expires_at=item.get("expires_at"),
                     filename=item.get("filename", ""))
        imported += 1
    return {"imported": imported, "skipped": skipped, "conflicts": conflicts,
            "corrupted": corrupted, "total": len(manifest.get("items", []))}
