"""Agent 注册表路由：清单查询 + 安装（ADR-0017/0018）

GET 列表登录即可；安装要求 boss。安装经 ATR 会话执行 scripts/agents/<name>.sh，
人在 Agent 终端观察安装过程与首次交互登录。
"""
from fastapi import APIRouter, Depends

from ..agents import agent_status, get_agent, list_agents
from ..atr import atr_request
from ..auth import current_user, require_boss

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def agents(user: dict = Depends(current_user)):
    return list_agents()


@router.post("/{name}/install")
async def install(name: str, user: dict = Depends(require_boss)):
    agent = get_agent(name)
    payload = {
        "id": f"install-{name}",
        "command": f"bash /opt/agent-install/{agent['install']}",
        "owner": "manager",
        "purpose": f"安装 agent：{name}",
        "env": {"HOME": f"/opt/agents/{name}"},
    }
    result = await atr_request("POST", "/sessions", payload)
    return {"ok": True, "session_id": f"install-{name}", **agent_status(name), "atr": result}
