"""Keycloak Admin REST 客户端（supervisor 侧管理操作：重置密码等）

凭据来自进程环境的 KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD（.env，NFR-002 不落代码）。
宿主回源走 127.0.0.1 + Host 头（同 oidc.py）；trust_env=False 防代理拦截。
"""
import os

import httpx
from fastapi import HTTPException

from .config import Cfg


async def _admin_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{Cfg.KC_INTERNAL}/realms/master/protocol/openid-connect/token",
        headers={"Host": Cfg.KC_HOST_HEADER},
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": os.environ.get("KEYCLOAK_ADMIN", "admin"),
              "password": os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")})
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Keycloak 管理员认证失败")
    return resp.json()["access_token"]


async def reset_password(username: str, new_password: str, temporary: bool = True):
    """管理员重置某用户密码（temporary=True 则用户下次登录须改密）"""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        token = await _admin_token(client)
        auth = {"Host": Cfg.KC_HOST_HEADER, "Authorization": f"Bearer {token}"}
        base = f"{Cfg.KC_INTERNAL}/admin/realms/{Cfg.KC_REALM}"

        resp = await client.get(f"{base}/users", headers=auth,
                                params={"username": username, "exact": "true"})
        users = resp.json() if resp.status_code == 200 else []
        if not users:
            raise HTTPException(status_code=404, detail=f"Keycloak 中不存在用户：{username}")

        resp = await client.put(f"{base}/users/{users[0]['id']}/reset-password",
                                headers=auth,
                                json={"type": "password", "value": new_password,
                                      "temporary": temporary})
        if resp.status_code not in (200, 204):
            raise HTTPException(status_code=502, detail=f"重置失败：{resp.text[:200]}")
