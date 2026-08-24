"""认证路由：登录跳转 / 回调 / 注销 / 当前用户"""
import secrets

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth import (
    create_session_cookie,
    exchange_code,
    oidc_authorize_url,
    oidc_logout_url,
    read_session_cookie,
)
from ..config import Cfg
from fastapi import Request

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 简易 state 防伪（MVP：内存态，重启即失效）
_pending_states: set[str] = set()


@router.get("/login")
async def login():
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    return RedirectResponse(oidc_authorize_url(state))


@router.get("/callback")
async def callback(code: str, state: str):
    if state not in _pending_states:
        raise HTTPException(status_code=400, detail="非法 state")
    _pending_states.discard(state)
    claims = await exchange_code(code)
    resp = RedirectResponse(Cfg.PUBLIC_URL + "/")
    resp.set_cookie(
        Cfg.SESSION_COOKIE,
        create_session_cookie(claims),
        max_age=Cfg.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(oidc_logout_url())
    resp.delete_cookie(Cfg.SESSION_COOKIE)
    return resp


@router.get("/me")
async def me(request: Request):
    user = read_session_cookie(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return JSONResponse(user)
