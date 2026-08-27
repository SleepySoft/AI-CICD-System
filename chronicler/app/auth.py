"""本地账密鉴权（FR-MGR-017）：PBKDF2 哈希 + itsdangerous 签名 cookie
鉴权后端抽象：verify()/current_user 之外的部分不感知后端形态，
Keycloak OIDC 后端作为可插拔实现预留（本版不接）。
"""
import hashlib
import hmac
import os
import time

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, TimestampSigner

from .config import Cfg
from .db import q1

_signer = TimestampSigner(Cfg.SESSION_SECRET)
_PBKDF2_ROUNDS = 200_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return f"pbkdf2${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt).split("$")[2], digest)


def make_session(username: str) -> str:
    return _signer.sign(username).decode()


def read_session(token: str) -> str | None:
    try:
        return _signer.unsign(token, max_age=Cfg.SESSION_MAX_AGE).decode()
    except BadSignature:
        return None


def current_user(request: Request) -> dict:
    token = request.cookies.get(Cfg.SESSION_COOKIE, "")
    username = read_session(token) if token else None
    user = q1("SELECT id, username, role FROM users WHERE username=?", (username,)) if username else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
