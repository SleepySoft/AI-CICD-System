"""OIDC 认证（Keycloak Authorization Code Flow）+ 会话 Cookie + 角色依赖"""
import time

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import Cfg

_serializer = URLSafeTimedSerializer(Cfg.SESSION_SECRET, salt="aisystem-session")


def create_session_cookie(claims: dict) -> str:
    return _serializer.dumps(claims)


def read_session_cookie(request: Request) -> dict | None:
    raw = request.cookies.get(Cfg.SESSION_COOKIE)
    if not raw:
        return None
    try:
        return _serializer.loads(raw, max_age=Cfg.SESSION_MAX_AGE)
    except BadSignature:
        return None


async def current_user(request: Request) -> dict:
    """依赖注入：要求已登录，返回 {sub, name, groups, roles...}"""
    user = read_session_cookie(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    return user


async def require_boss(user: dict = Depends(current_user)) -> dict:
    """依赖注入：要求 boss 组（管理操作/敏感内容）"""
    if Cfg.BOSS_GROUP not in user.get("groups", []):
        raise HTTPException(status_code=403, detail="需要 boss 权限")
    return user


def oidc_authorize_url(state: str) -> str:
    redirect_uri = f"{Cfg.PUBLIC_URL}/api/auth/callback"
    return (
        f"{Cfg.realm_url(public=True)}/protocol/openid-connect/auth"
        f"?client_id={Cfg.OIDC_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code&scope=openid%20profile%20email%20groups"
        f"&state={state}"
    )


async def exchange_code(code: str) -> dict:
    """用授权码换 token，返回 id_token 中的 claims"""
    redirect_uri = f"{Cfg.PUBLIC_URL}/api/auth/callback"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{Cfg.realm_url(public=False)}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": Cfg.OIDC_CLIENT_ID,
                "client_secret": Cfg.OIDC_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail=f"OIDC token 交换失败: {resp.text[:200]}")
    id_token = resp.json()["id_token"]
    # token 直接来自可信的 token endpoint（内网回源），此处只解析 claims
    claims = jwt.decode(id_token, options={"verify_signature": False})
    return {
        "sub": claims.get("sub"),
        "name": claims.get("preferred_username") or claims.get("name"),
        "email": claims.get("email", ""),
        "groups": claims.get("groups", []),
        "iat": int(time.time()),
    }


def oidc_logout_url() -> str:
    return (
        f"{Cfg.realm_url(public=True)}/protocol/openid-connect/logout"
        f"?post_logout_redirect_uri={Cfg.PUBLIC_URL}"
        f"&client_id={Cfg.OIDC_CLIENT_ID}"
    )
