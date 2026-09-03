"""一次性引导能力：短期 cookie，完成后永久失效。"""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, TimestampSigner

from ..config import Cfg
from . import store

COOKIE = "chronicler_bootstrap"
MAX_AGE = 24 * 3600
_issued_code = ""


def _security_dir() -> Path:
    path = Cfg.DATA / "initialization"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _signer() -> TimestampSigner:
    path = _security_dir() / "session.key"
    if not path.is_file():
        path.write_bytes(secrets.token_bytes(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return TimestampSigner(path.read_bytes())


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def issue_code() -> str:
    """每次 bootstrap 进程启动轮换引导码；明文只存在于当前进程。"""
    global _issued_code
    inst = store.ensure_installation()
    if inst["bootstrap_closed_at"]:
        return ""
    _issued_code = secrets.token_urlsafe(24)
    store.execute("UPDATE installation SET bootstrap_token_hash=?,updated_at=? WHERE id=1",
                  (_digest(_issued_code), time.time()))
    return _issued_code


def exchange(code: str) -> str:
    with store.transaction() as conn:
        row = conn.execute("SELECT bootstrap_closed_at,bootstrap_token_hash FROM installation WHERE id=1").fetchone()
        if not row or row["bootstrap_closed_at"]:
            raise HTTPException(status_code=410, detail="初始化入口已关闭")
        if not code or not hmac.compare_digest(_digest(code), row["bootstrap_token_hash"]):
            raise HTTPException(status_code=401, detail="引导码无效、已使用或已轮换")
        conn.execute("UPDATE installation SET bootstrap_token_hash='',updated_at=? WHERE id=1", (time.time(),))
    return _signer().sign(f"bootstrap:{int(time.time())}").decode()


def require_setup_session(request: Request):
    inst = store.installation()
    if not inst:
        raise HTTPException(status_code=401, detail="初始化状态不存在")
    if inst["bootstrap_closed_at"]:
        from ..auth import current_user
        user = current_user(request)
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user
    token = request.cookies.get(COOKIE, "")
    try:
        value = _signer().unsign(token, max_age=MAX_AGE).decode()
        if not value.startswith("bootstrap:"):
            raise BadSignature("wrong scope")
    except BadSignature:
        raise HTTPException(status_code=401, detail="请使用控制台显示的引导链接解锁")
    return {"role": "bootstrap", "username": "bootstrap"}