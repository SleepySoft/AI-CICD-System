"""秘密库存储层：元数据透明，值只存 age 密文（FR-INIT-014/015）。

密文存于 chronicler.db（data/private/chronicler/）——落盘的是密文而非明文，
与"机密（明文）永不落 data"约束一致；主密钥在 data/ 之外的 secrets/master.key。

锁定语义（docs/how/secrets-vault.md §3.5）：库中已有秘密而主密钥缺失或不匹配时，
一切写入/解密拒绝并抛 VaultLocked——绝不静默生成新密钥让旧数据变砖。
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


class VaultLocked(RuntimeError):
    """库中已有秘密但主密钥缺失/不匹配。reason: master-key-missing | master-key-mismatch"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__({"master-key-missing": "存在既有秘密数据，但主密钥缺失",
                          "master-key-mismatch": "存在既有秘密数据，但当前主密钥无法解密"}[reason])


# ---------- 锁定与钥匙 ----------

def count() -> int:
    return q1("SELECT COUNT(*) AS n FROM vault_secrets")["n"]


def _identity_verified() -> "crypto.x25519.Identity":
    """取可用主密钥：库空才允许生成新钥；库非空必须能解密抽样记录，否则锁定。"""
    identity = crypto.load_identity()
    n = count()
    if identity is None:
        if n:
            raise VaultLocked("master-key-missing")
        identity = crypto.generate_identity()
        meta_set("key_acked", "")  # 新钥匙进入“未交接”状态
        return identity
    if n:
        sample = q1("SELECT ciphertext FROM vault_secrets ORDER BY id LIMIT 1")
        try:
            crypto.decrypt(sample["ciphertext"], identity)
        except Exception:
            raise VaultLocked("master-key-mismatch")
    return identity


def lock_state() -> dict:
    """锁定状态探测（只读，供状态接口）。"""
    n = count()
    identity = crypto.load_identity()
    state = {"count": n, "has_key": identity is not None,
             "recipient": crypto.recipient_str(identity), "locked": False, "reason": "",
             "key_acked": bool(meta_get("key_acked"))}
    if n and identity is None:
        state.update(locked=True, reason="master-key-missing")
    elif n and identity is not None:
        sample = q1("SELECT ciphertext FROM vault_secrets ORDER BY id LIMIT 1")
        try:
            crypto.decrypt(sample["ciphertext"], identity)
        except Exception:
            state.update(locked=True, reason="master-key-mismatch")
    return state


def try_unlock(key_text: str) -> str:
    """收养 admin 提交的主密钥：验证能解密既有秘密后落盘。返回接收者公钥。"""
    identity = crypto.parse_identity(key_text)  # 格式错误抛 ValueError
    n = count()
    if n:
        sample = q1("SELECT ciphertext FROM vault_secrets ORDER BY id LIMIT 1")
        try:
            crypto.decrypt(sample["ciphertext"], identity)
        except Exception:
            raise ValueError("密钥与既有秘密数据不匹配")
    crypto.write_identity(identity)
    return str(identity.to_public())


def ack_key(key_text: str) -> bool:
    """交接确认：admin 粘贴回主密钥证明已收存（prove possession）。"""
    identity = crypto.load_identity()
    if identity is None:
        return False
    import hmac
    if hmac.compare_digest(key_text.strip(), str(identity)):
        meta_set("key_acked", "1")
        return True
    return False


def meta_get(key: str) -> str:
    row = q1("SELECT value FROM vault_meta WHERE key=?", (key,))
    return row["value"] if row else ""


def meta_set(key: str, value: str):
    execute("INSERT INTO vault_meta(key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------- 元数据 CRUD ----------

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


def find(scope: str, name: str) -> dict | None:
    return q1("SELECT * FROM vault_secrets WHERE scope=? AND name=?", (scope, name))


def create(kind: str, name: str, scope: str, plain: bytes, actor: str,
           secret_type: str = "password", rotation_risk: str = "coordinated",
           summary: str = "", owner: str = "", expires_at: float | None = None,
           filename: str = "") -> int:
    validate_meta(name, scope, kind, secret_type, rotation_risk)
    if not plain:
        raise ValueError("值不能为空")
    if find(scope, name):
        raise ValueError(f"同名秘密已存在：{scope}/{name}")
    identity = _identity_verified()
    digest = hashlib.sha256(plain).hexdigest()
    now = time.time()
    return execute(
        "INSERT INTO vault_secrets(name, scope, kind, secret_type, rotation_risk, summary, owner,"
        " expires_at, filename, size, sha256, ciphertext, created_by, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, scope, kind, secret_type, rotation_risk, summary, owner, expires_at, filename,
         len(plain), digest, crypto.encrypt(plain, identity), actor, now, now))


def upsert(kind: str, name: str, scope: str, plain: bytes, actor: str, **meta) -> str:
    """双写/导入用：不存在则建，值同则跳过，值异则轮换。返回 created|updated|unchanged。"""
    row = find(scope, name)
    digest = hashlib.sha256(plain).hexdigest()
    if row and row["sha256"] == digest:
        return "unchanged"
    if row:
        replace_value(row["id"], plain)
        return "updated"
    create(kind=kind, name=name, scope=scope, plain=plain, actor=actor, **meta)
    return "created"


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
    identity = _identity_verified()
    execute("UPDATE vault_secrets SET ciphertext=?, size=?, sha256=?, updated_at=? WHERE id=?",
            (crypto.encrypt(plain, identity), len(plain),
             hashlib.sha256(plain).hexdigest(), time.time(), sid))


def decrypt_value(row: dict) -> bytes:
    identity = _identity_verified()
    return crypto.decrypt(row["ciphertext"], identity)


def delete(sid: int) -> dict | None:
    row = get_meta(sid)
    if row:
        execute("DELETE FROM vault_secrets WHERE id=?", (sid,))
    return row
