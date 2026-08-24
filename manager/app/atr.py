"""ATR（terminal-runtime）客户端：Manager 作为带鉴权的代理访问 18650"""
import httpx
from fastapi import HTTPException
from fastapi.responses import Response

from .config import Cfg


def _headers() -> dict:
    return {"Authorization": f"Bearer {Cfg.ATR_TOKEN}"} if Cfg.ATR_TOKEN else {}


async def atr_request(method: str, path: str, json_body: dict | None = None) -> dict:
    url = f"{Cfg.ATR_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, json=json_body, headers=_headers())
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ATR 不可达: {e}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
    return resp.json()


async def atr_text(path: str) -> Response:
    url = f"{Cfg.ATR_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_headers())
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ATR 不可达: {e}")
    return Response(content=resp.text, status_code=resp.status_code, media_type="text/plain; charset=utf-8")
