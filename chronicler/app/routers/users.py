"""用户管理（仅 admin，FR-MGR-017）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import hash_password, require_admin
from ..db import audit, execute, q, q1

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


class UserBody(BaseModel):
    username: str
    password: str
    role: str = "user"  # admin | user


@router.get("")
async def list_users():
    return q("SELECT id, username, role, created_at FROM users ORDER BY id")


@router.post("")
async def create_user(body: UserBody):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role 仅支持 admin/user")
    if q1("SELECT id FROM users WHERE username=?", (body.username,)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    uid = execute("INSERT INTO users(username, password_hash, role, created_at)"
                  " VALUES (?,?,?,strftime('%s','now'))",
                  (body.username, hash_password(body.password), body.role))
    audit("admin", "user.create", body.username)
    return {"id": uid, "username": body.username, "role": body.role}


@router.delete("/{uid}")
async def delete_user(uid: int):
    user = q1("SELECT username FROM users WHERE id=?", (uid,))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if q1("SELECT COUNT(*) AS n FROM users WHERE role='admin'")["n"] <= 1 \
            and q1("SELECT role FROM users WHERE id=?", (uid,))["role"] == "admin":
        raise HTTPException(status_code=400, detail="不能删除最后一个 admin")
    execute("DELETE FROM users WHERE id=?", (uid,))
    audit("admin", "user.delete", user["username"])
    return {"ok": True}
