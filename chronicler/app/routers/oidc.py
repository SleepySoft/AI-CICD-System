"""Keycloak OIDC 后端（FR-MGR-017 可插拔后端之一；ADR-0023 预留接口的实现）

启用方式：.env 设 CHRONICLER_AUTH_BACKEND=oidc + CHRONICLER_OIDC_SECRET（与
Keycloak chronicler 客户端一致，scripts/wire-chronicler.sh 创建）。
宿主侧回源：supervisor 在 docker 宿主，token 交换走 127.0.0.1 + Host 头
（Keycloak 已开 KC_HOSTNAME_BACKCHANNEL_DYNAMIC），不新开容器端口。
角色映射：Keycloak groups → boss=admin / 其余=user。
"""
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .. import auth
from ..config import Cfg
from ..db import audit, execute, q1

router = APIRouter(prefix="/api/auth/oidc", tags=["auth-oidc"])
_state = URLSafeTimedSerializer(Cfg.SESSION_SECRET + ":oidc")


def _realm_url(public: bool) -> str:
    base = Cfg.KC_PUBLIC if public else Cfg.KC_INTERNAL
    return f"{base}/realms/{Cfg.KC_REALM}/protocol/openid-connect"


def _headers(public: bool) -> dict:
    """宿主回源：KC_INTERNAL 为 127.0.0.1 时用 Host 头伪装域名"""
    return {} if public else {"Host": Cfg.KC_HOST_HEADER}


@router.get("/login")
async def oidc_login():
    if Cfg.AUTH_BACKEND != "oidc":
        raise HTTPException(status_code=400, detail="未启用 OIDC 后端")
    state = _state.dumps({"t": time.time()})
    url = (f"{_realm_url(public=True)}/auth?client_id={Cfg.OIDC_CLIENT_ID}"
           f"&redirect_uri={Cfg.PUBLIC_URL}/api/auth/oidc/callback"
           f"&response_type=code&scope=openid%20profile%20email%20groups&state={state}")
    return RedirectResponse(url)


@router.get("/callback")
async def oidc_callback(code: str, state: str):
    if Cfg.AUTH_BACKEND != "oidc":
        raise HTTPException(status_code=400, detail="未启用 OIDC 后端")
    try:
        _state.loads(state, max_age=600)
    except BadSignature:
        raise HTTPException(status_code=400, detail="state 无效或过期") from None

    async with httpx.AsyncClient(timeout=10) as client:
        tok = await client.post(f"{_realm_url(public=False)}/token",
                                headers=_headers(public=False),
                                data={"grant_type": "authorization_code", "code": code,
                                      "client_id": Cfg.OIDC_CLIENT_ID,
                                      "client_secret": Cfg.OIDC_CLIENT_SECRET,
                                      "redirect_uri": f"{Cfg.PUBLIC_URL}/api/auth/oidc/callback"})
        if tok.status_code != 200:
            raise HTTPException(status_code=401, detail=f"token 交换失败：{tok.text[:200]}")
        info = await client.get(f"{_realm_url(public=False)}/userinfo",
                                headers={**_headers(public=False),
                                         "Authorization": f"Bearer {tok.json()['access_token']}"})
        if info.status_code != 200:
            raise HTTPException(status_code=401, detail="userinfo 获取失败")

    claims = info.json()
    username = claims.get("preferred_username") or claims.get("email")
    if not username:
        raise HTTPException(status_code=401, detail="无法确定用户身份")
    groups = [g.strip("/") for g in claims.get("groups", [])]
    role = "admin" if "boss" in groups else "user"

    # 自动 provisioning：首次 OIDC 登录落本地用户记录（密码哈希为空 = 仅 OIDC 可登录）
    user = q1("SELECT id, role FROM users WHERE username=?", (username,))
    if not user:
        execute("INSERT INTO users(username, password_hash, role, created_at)"
                " VALUES (?,?,?,strftime('%s','now'))", (username, "", role))
    elif user["role"] != role:
        execute("UPDATE users SET role=? WHERE username=?", (role, username))

    audit(username, "login.oidc", detail=f"groups={groups}")
    resp = RedirectResponse("/")
    resp.set_cookie(Cfg.SESSION_COOKIE, auth.make_session(username),
                    max_age=Cfg.SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp
