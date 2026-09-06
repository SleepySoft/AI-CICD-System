"""用户管理（仅 admin，FR-MGR-017）

OIDC 模式下账号事实源为 Keycloak：本地表只是首次登录自动建档的影子记录，
本路由只读；增删返回 400（应急后门走 CLI create-admin）。local 模式下可正常增删。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import hash_password, require_admin
from ..config import Cfg
from ..db import audit, execute, q, q1
from .. import component_exec

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


class UserBody(BaseModel):
    username: str
    password: str
    role: str = "user"  # admin | user


def _with_source(row: dict) -> dict:
    row["source"] = "local" if row.get("password_hash") else "oidc"
    row.pop("password_hash", None)
    return row


@router.get("")
async def list_users():
    return [_with_source(r) for r in q("SELECT id, username, role, password_hash, created_at FROM users ORDER BY id")]


def _reject_if_oidc():
    if Cfg.AUTH_BACKEND == "oidc":
        raise HTTPException(status_code=400, detail="OIDC 模式下账号由 Keycloak 统一管理（sso.localhost/admin）；本地增删已关闭")


@router.post("")
async def create_user(body: UserBody):
    _reject_if_oidc()
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role 仅支持 admin/user")
    if q1("SELECT id FROM users WHERE username=?", (body.username,)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    uid = execute("INSERT INTO users(username, password_hash, role, created_at)"
                  " VALUES (?,?,?,strftime('%s','now'))",
                  (body.username, hash_password(body.password), body.role))
    audit("admin", "user.create", body.username)
    return {"id": uid, "username": body.username, "role": body.role}


class ResetPasswordBody(BaseModel):
    password: str
    temporary: bool = True   # True=用户下次登录须改密（推荐，管理员不长期持有他人口令）


@router.post("/{username}/reset-password")
async def reset_password(username: str, body: ResetPasswordBody):
    """管理员重置用户密码：由提供 hooks/users.py 能力的身份组件执行（ADR-0027 能力脚本）。"""
    if Cfg.AUTH_BACKEND != "oidc":
        raise HTTPException(status_code=400, detail="仅 OIDC 模式可用；local 模式请删除后重建用户")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if not q1("SELECT id FROM users WHERE username=?", (username,)):
        raise HTTPException(status_code=404, detail="用户不存在")
    import asyncio
    args = ["reset-password", username, body.password] + ([] if body.temporary else ["--permanent"])
    result = await asyncio.to_thread(component_exec.run_capability, "users.py", args)
    if result is None:
        raise HTTPException(status_code=400, detail="当前部署的身份组件不支持在线重置密码")
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=f"重置失败：{result.get('error', '')[:200]}")
    audit("admin", "user.reset_password", username, f"temporary={body.temporary}")
    return {"ok": True, "username": username}


@router.delete("/{uid}")
async def delete_user(uid: int):
    _reject_if_oidc()
    user = q1("SELECT username FROM users WHERE id=?", (uid,))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if q1("SELECT COUNT(*) AS n FROM users WHERE role='admin'")["n"] <= 1 \
            and q1("SELECT role FROM users WHERE id=?", (uid,))["role"] == "admin":
        raise HTTPException(status_code=400, detail="不能删除最后一个 admin")
    execute("DELETE FROM users WHERE id=?", (uid,))
    audit("admin", "user.delete", user["username"])
    return {"ok": True}
