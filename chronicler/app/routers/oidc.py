"""Keycloak OIDC 后端（FR-MGR-017 可插拔后端之一；ADR-0023 预留接口的实现）

启用方式：.env 设 CHRONICLER_AUTH_BACKEND=oidc + CHRONICLER_OIDC_SECRET（与
Keycloak chronicler 客户端一致，scripts/wire-chronicler.sh 创建）。
宿主侧回源：supervisor 在 docker 宿主，token 交换走 127.0.0.1 + Host 头
（Keycloak 已开 KC_HOSTNAME_BACKCHANNEL_DYNAMIC），不新开容器端口。
角色映射：Keycloak groups → boss=admin / 其余=user。
"""
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .. import auth
from ..config import Cfg
from ..db import audit, execute, q1

router = APIRouter(prefix="/api/auth/oidc", tags=["auth-oidc"])
_state = URLSafeTimedSerializer(Cfg.SESSION_SECRET + ":oidc")


def refresh_serializer():
    """同 auth.refresh_signer：秘密库解析出真实会话密钥后重建（ADR-0045）。"""
    global _state
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
async def oidc_callback(request: Request, code: str | None = None, state: str = "",
                        error: str | None = None, error_description: str | None = None):
    if Cfg.AUTH_BACKEND != "oidc":
        raise HTTPException(status_code=400, detail="未启用 OIDC 后端")
    if error or not code:
        # Keycloak 拒绝时回跳 error 参数（如 invalid_scope），友好呈现而非 422
        raise HTTPException(status_code=401,
                            detail=f"OIDC 授权失败：{error or '缺少 code'}（{error_description or ''}）")
    try:
        _state.loads(state, max_age=600)
    except BadSignature:
        raise HTTPException(status_code=400, detail="state 无效或过期") from None

    # trust_env=False：不读取 http_proxy 等环境变量——宿主回源是内网直连，
    # 经 Clash 类代理会被拦（no_proxy 的 127.* glob 模式 httpx 不认）
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        tok = await client.post(f"{_realm_url(public=False)}/token",
                                headers=_headers(public=False),
                                data={"grant_type": "authorization_code", "code": code,
                                      "client_id": Cfg.OIDC_CLIENT_ID,
                                      "client_secret": Cfg.OIDC_CLIENT_SECRET,
                                      "redirect_uri": f"{Cfg.PUBLIC_URL}/api/auth/oidc/callback"})
        if tok.status_code != 200:
            # 重放容错（2026-09-06 实测）：浏览器模拟插件/刷新会重复请求回调，
            # code 一次性已被首次消费（Keycloak: invalid_grant/already used）。
            # 若请求已带有效会话 cookie（首次成功所发），视为重放直接放行。
            if "invalid_grant" in tok.text or "already used" in tok.text:
                existing = auth.read_session(request.cookies.get(Cfg.SESSION_COOKIE, ""))
                if existing:
                    return RedirectResponse("/")
            raise HTTPException(status_code=401,
                                detail="登录链接已使用或过期，请回到首页重新发起登录"
                                       f"（{tok.text[:160]}）")
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
