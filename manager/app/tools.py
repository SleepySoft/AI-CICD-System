"""环境工具注册表（tools.yaml）+ Docker 状态/启停 + 健康探测"""
import asyncio
from functools import lru_cache

import docker
import httpx
import yaml
from fastapi import HTTPException

from .config import Cfg


def load_tools() -> list[dict]:
    with open(Cfg.TOOLS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)["tools"]


@lru_cache(maxsize=1)
def _docker() -> docker.DockerClient:
    return docker.from_env()


def container_status(container_name: str | None) -> str:
    """running / stopped / absent"""
    if not container_name:
        return "external"
    try:
        c = _docker().containers.get(container_name)
        return "running" if c.status == "running" else "stopped"
    except docker.errors.NotFound:
        return "absent"
    except docker.errors.DockerException:
        return "unknown"


async def http_healthy(url: str | None) -> bool | None:
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(url)
            return resp.status_code < 500
    except Exception:
        return False


async def list_tools(user: dict) -> list[dict]:
    tools = load_tools()
    is_boss = Cfg.BOSS_GROUP in user.get("groups", [])

    async def enrich(t: dict) -> dict | None:
        if t.get("visibility") == "boss" and not is_boss:
            return None
        status = container_status(t.get("container"))
        healthy = await http_healthy(t.get("health_url")) if status == "running" else None
        return {**t, "status": status, "healthy": healthy}

    enriched = await asyncio.gather(*(enrich(t) for t in tools))
    return [t for t in enriched if t is not None]


def control_tool(name: str, action: str) -> dict:
    tool = next((t for t in load_tools() if t["name"] == name), None)
    if not tool:
        raise HTTPException(status_code=404, detail="未知工具")
    container = tool.get("container")
    if not container:
        raise HTTPException(status_code=400, detail="该工具不由本环境管理")
    try:
        c = _docker().containers.get(container)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="容器未部署（对应 profile 未启用）")
    if action == "start":
        c.start()
    elif action == "stop":
        c.stop(timeout=10)
    elif action == "restart":
        c.restart(timeout=10)
    else:
        raise HTTPException(status_code=400, detail="不支持的操作")
    return {"ok": True, "name": name, "action": action}
