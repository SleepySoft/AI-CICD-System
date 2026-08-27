"""工具面板路由（FR-MGR-001）：状态查看全员，启停仅 admin"""
from fastapi import APIRouter, Depends

from .. import tools
from ..auth import current_user, require_admin
from ..db import audit

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def list_(user: dict = Depends(current_user)):
    return tools.list_tools(user)


@router.post("/{name}/{action}")
async def control(name: str, action: str, user: dict = Depends(require_admin)):
    result = tools.control_tool(name, action)
    audit(user["username"], f"tool.{action}", name)
    return result
