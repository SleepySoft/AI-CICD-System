"""工具总览路由：列表（含状态）+ 启停控制"""
from fastapi import APIRouter, Depends

from ..auth import current_user, require_boss
from ..tools import control_tool, list_tools

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
async def get_tools(user: dict = Depends(current_user)):
    return await list_tools(user)


@router.post("/{name}/{action}")
async def post_tool_action(name: str, action: str, user: dict = Depends(require_boss)):
    return control_tool(name, action)
