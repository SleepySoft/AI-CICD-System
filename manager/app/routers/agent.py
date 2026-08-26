"""Agent 终端路由：透传 ATR（terminal-runtime）会话原语
所有接口需登录；创建/操作会话要求 boss（dev 只读观察）。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..agents import build_session_payload, get_agent
from ..atr import atr_request, atr_text
from ..auth import current_user, require_boss

router = APIRouter(prefix="/api/agent", tags=["agent"])


class CreateSession(BaseModel):
    id: str
    command: str = "bash"
    agent: str | None = None   # 指定注册表 agent（agents.yaml）时覆盖 command 并注入 env
    rows: int = 40
    cols: int = 120
    owner: str = "manager"
    purpose: str = ""


class Action(BaseModel):
    type: str            # submit | text | paste | key | control | resize
    text: str | None = None
    key: str | None = None
    rows: int | None = None
    cols: int | None = None


class Wait(BaseModel):
    until: str = "screen_stable"   # screen_stable | input_likely_ready | process_exit
    timeout_ms: int = 15000
    stable_ms: int = 800


@router.get("/health")
async def atr_health(user: dict = Depends(current_user)):
    return await atr_request("GET", "/health")


@router.get("/sessions")
async def list_sessions(user: dict = Depends(current_user)):
    return await atr_request("GET", "/sessions")


@router.post("/sessions")
async def create_session(body: CreateSession, user: dict = Depends(require_boss)):
    payload = body.model_dump(exclude_none=True)
    if body.agent:
        payload.pop("agent")
        payload.update(build_session_payload(get_agent(body.agent)))
        payload["purpose"] = payload["purpose"] or f"agent:{body.agent}"
    return await atr_request("POST", "/sessions", payload)


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, user: dict = Depends(require_boss)):
    return await atr_request("DELETE", f"/sessions/{sid}")


@router.get("/sessions/{sid}/observe")
async def observe(sid: str, user: dict = Depends(current_user)):
    return await atr_request("GET", f"/sessions/{sid}/observe")


@router.get("/sessions/{sid}/screenshot")
async def screenshot(sid: str, user: dict = Depends(current_user)):
    return await atr_text(f"/sessions/{sid}/screenshot")


@router.post("/sessions/{sid}/actions")
async def act(sid: str, body: Action, user: dict = Depends(require_boss)):
    payload = {
        "actor": user.get("name", "manager"),
        "action": body.model_dump(exclude_none=True),
    }
    return await atr_request("POST", f"/sessions/{sid}/actions", payload)


@router.post("/sessions/{sid}/wait")
async def wait(sid: str, body: Wait, user: dict = Depends(current_user)):
    return await atr_request("POST", f"/sessions/{sid}/wait", body.model_dump())
