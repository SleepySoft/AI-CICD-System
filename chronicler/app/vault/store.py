"""秘密库存储层：元数据透明，值只存 age 密文（FR-INIT-014/015）。

密文存于 chronicler.db（data/private/chronicler/）——落盘的是密文而非明文，
与"机密（明文）永不落 data"约束一致；主密钥在 data/ 之外的 secrets/master.key。
"""
import hashlib
import re
import time

from ..db import execute, q, q1
from . import crypto

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SECRET_TYPES = {"password", "client-secret", "encryption-key", "api-token", "access-key", "certificate"}
ROTATION_RISKS = {"low", "coordinated", "critical"}
KINDS = {"text", "file"}

META_COLS = ("id, name, scope, kind, secret_type, rotation_risk, summary, owner, "
             "expires_at, filename, size, sha256, created_by, created_at, updated_at")


def validate_meta(name: str, scope: str, kind: str, secret_type: str, rotation_risk: str):
    if not _NAME_RE.match(name or ""):
        raise ValueError("名称需为英数开头，可含 . _ -，最长 64 字符")
    if not _SCOPE_RE.match(scope or ""):
        raise ValueError("作用域需为小写英数/连字符，最长 64 字符")
    if kind not in KINDS:
        raise ValueError(f"kind 仅支持 {'/'.join(sorted(KINDS))}")
    if secret_type not in SECRET_TYPES:
        raise ValueError(f"secret_type 仅支持 {'/'.join(sorted(SECRET_TYPES))}")
    if rotation_risk not in ROTATION_RISKS:
        raise ValueError(f"rotation_risk 仅支持 {'/'.join(sorted(ROTATION_RISKS))}")


def list_meta(scope: str = "") -> list[dict]:
    if scope:
        return q(f"SELECT {META_COLS} FROM vault_secrets WHERE scope=? ORDER BY scope, name", (scope,))
    return q(f"SELECT {META_COLS} FROM vault_secrets ORDER BY scope, name")


def get_meta(sid: int) -> dict | None:
    return q1(f"SELECT {META_COLS} FROM vault_secrets WHERE id=?", (sid,))


def all_rows() -> list[dict]:
    return q("SELECT * FROM vault_secrets ORDER BY scope, name")


def get_row(sid: int) -> dict | None:
    return q1("SELECT * FROM vault_secrets WHERE id=?", (sid,))


def create(kind: str, name: str, scope: str, plain: bytes, actor: str,
           secret_type: str = "password", rotation_risk: str = "coordinated",
           summary: str = "", owner: str = "", expires_at: float | None = None,
           filename: str = "") -> int:
    validate_meta(name, scope, kind, secret_type, rotation_risk)
    if not plain:
        raise ValueError("值不能为空")
    if q1("SELECT id FROM vault_secrets WHERE scope=? AND name=?", (scope, name)):
        raise ValueError(f"同名秘密已存在：{scope}/{name}")
    digest = hashlib.sha256(plain).hexdigest()
    now = time.time()
    return execute(
        "INSERT INTO vault_secrets(name, scope, kind, secret_type, rotation_risk, summary, owner,"
        " expires_at, filename, size, sha256, ciphertext, created_by, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, scope, kind, secret_type, rotation_risk, summary, owner, expires_at, filename,
         len(plain), digest, crypto.encrypt(plain), actor, now, now))


def update_meta(sid: int, fields: dict) -> bool:
    allowed = {"summary", "owner", "expires_at", "secret_type", "rotation_risk"}
    sets, args = [], []
    for key in allowed & fields.keys():
        if key == "secret_type" and fields[key] not in SECRET_TYPES:
            raise ValueError("secret_type 非法")
        if key == "rotation_risk" and fields[key] not in ROTATION_RISKS:
            raise ValueError("rotation_risk 非法")
        sets.append(f"{key}=?")
        args.append(fields[key])
    if not sets:
        return False
    sets.append("updated_at=?")
    args.append(time.time())
    args.append(sid)
    execute(f"UPDATE vault_secrets SET {', '.join(sets)} WHERE id=?", tuple(args))
    return True


def replace_value(sid: int, plain: bytes) -> None:
    """轮换值：旧值随密文覆盖不可恢复（recover 语义见 ADR-0040）。"""
    if not plain:
        raise ValueError("值不能为空")
    execute("UPDATE vault_secrets SET ciphertext=?, size=?, sha256=?, updated_at=? WHERE id=?",
            (crypto.encrypt(plain), len(plain), hashlib.sha256(plain).hexdigest(), time.time(), sid))


def decrypt_value(row: dict) -> bytes:
    return crypto.decrypt(row["ciphertext"])


def delete(sid: int) -> dict | None:
    row = get_meta(sid)
    if row:
        execute("DELETE FROM vault_secrets WHERE id=?", (sid,))
    return row
