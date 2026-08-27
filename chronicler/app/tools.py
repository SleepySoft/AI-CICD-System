"""工具面板（FR-MGR-001）：docker 本地 socket 直连（ADR-0020：supervisor 与 dockerd 同环境）"""
import docker
import yaml
from fastapi import HTTPException

from .config import Cfg

_docker = None


def _client() -> docker.DockerClient:
    global _docker
    if _docker is None:
        _docker = docker.from_env()
    return _docker


def load_tools() -> list[dict]:
    override = Cfg.DATA / "config" / "tools.yaml"
    path = override if override.is_file() else Cfg.CONFIG_DIR / "tools.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["tools"]


def container_status(name: str | None) -> str:
    if not name:
        return "external"
    try:
        c = _client().containers.get(name)
        return "running" if c.status == "running" else "stopped"
    except docker.errors.NotFound:
        return "absent"
    except docker.errors.DockerException:
        return "unknown"


def list_tools(user: dict) -> list[dict]:
    out = []
    for t in load_tools():
        if t.get("visibility") == "admin" and user["role"] != "admin":
            continue
        out.append({**t, "status": container_status(t.get("container"))})
    return out


def control_tool(name: str, action: str) -> dict:
    tool = next((t for t in load_tools() if t["name"] == name), None)
    if not tool:
        raise HTTPException(status_code=404, detail="未知工具")
    container = tool.get("container")
    if not container:
        raise HTTPException(status_code=400, detail="该工具不由本环境管理")
    try:
        c = _client().containers.get(container)
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
