"""鉴权路由：本地账密登录/登出（FR-MGR-017）"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from .. import auth
from ..config import Cfg
from ..db import audit, q1

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.get("/method")
async def method():
    """前端登录页据此决定展示本地表单还是 SSO 按钮"""
    return {"backend": Cfg.AUTH_BACKEND}


@router.post("/login")
async def login(body: LoginBody, response: Response):
    user = q1("SELECT * FROM users WHERE username=?", (body.username,))
    if not user or not user["password_hash"] or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    response.set_cookie(Cfg.SESSION_COOKIE, auth.make_session(user["username"]),
                        max_age=Cfg.SESSION_MAX_AGE, httponly=True, samesite="lax")
    audit(user["username"], "login")
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(Cfg.SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(auth.current_user)):
    return user
