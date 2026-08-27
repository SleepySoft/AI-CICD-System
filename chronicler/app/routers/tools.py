"""组件路由（FR-MGR-001/022）：状态/日志/详情登录可读；启停/自启开关仅 admin"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import tools
from ..auth import current_user, require_admin
from ..db import audit

router = APIRouter(prefix="/api/tools", tags=["tools"])


class AutostartBody(BaseModel):
    enabled: bool


@router.get("")
async def list_(user: dict = Depends(current_user)):
    return tools.list_tools(user)


@router.post("/{name}/autostart")
async def set_autostart(name: str, body: AutostartBody, user: dict = Depends(require_admin)):
    result = tools.set_autostart(name, body.enabled)
    audit(user["username"], "tool.autostart", name, f"enabled={body.enabled}")
    return result


@router.post("/{name}/{action}")
async def control(name: str, action: str, user: dict = Depends(require_admin)):
    result = tools.control_tool(name, action)
    audit(user["username"], f"tool.{action}", name)
    return result


@router.get("/{name}/logs", response_class=PlainTextResponse)
async def logs(name: str, tail: int = 300, user: dict = Depends(current_user)):
    return tools.tool_logs(name, tail)


@router.get("/{name}/detail")
async def detail(name: str, user: dict = Depends(current_user)):
    return tools.tool_detail(name)
