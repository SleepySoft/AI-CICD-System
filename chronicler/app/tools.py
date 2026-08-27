"""组件插件注册与生命周期管理（FR-MGR-001 状态/启停 + FR-MGR-022 自启/日志/详情/插件化）

插件化：chronicler/config/tools.d/*.yaml 一个文件一个组件；
data/chronicler/config/tools.d/*.yaml 为用户目录（同名覆盖内置）。
自启开关持久化在 data/chronicler/config/autostart.yaml（运行时覆盖层）。
docker 控制走本地 socket（ADR-0020：supervisor 与 dockerd 同环境）。
"""
import time

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


def _load_dir(d) -> dict:
    out = {}
    if d.is_dir():
        for f in sorted(d.glob("*.yaml")):
            with open(f, encoding="utf-8") as fh:
                entry = yaml.safe_load(fh)
            if entry and entry.get("name"):
                out[entry["name"]] = entry
    return out


def load_tools() -> list[dict]:
    """合并 内置 tools.d + 用户 tools.d + autostart 覆盖层，字段归一化"""
    merged = _load_dir(Cfg.CONFIG_DIR / "tools.d")
    merged.update(_load_dir(Cfg.DATA / "config" / "tools.d"))
    overlay = _autostart_overlay()
    tools = []
    for t in merged.values():
        t.setdefault("autostart", False)
        t.setdefault("critical", False)
        t.setdefault("visibility", "all")
        t["driver"] = t.get("driver") or ("docker" if t.get("container") else "external")
        if t["name"] in overlay:
            t["autostart"] = overlay[t["name"]]
        tools.append(t)
    return tools


def get_tool(name: str) -> dict:
    tool = next((t for t in load_tools() if t["name"] == name), None)
    if not tool:
        raise HTTPException(status_code=404, detail="未知组件")
    return tool


# ---------- 自启开关 ----------

def _autostart_path():
    p = Cfg.DATA / "config" / "autostart.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _autostart_overlay() -> dict:
    p = _autostart_path()
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def set_autostart(name: str, enabled: bool) -> dict:
    tool = get_tool(name)
    overlay = _autostart_overlay()
    overlay[name] = bool(enabled)
    with open(_autostart_path(), "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(overlay, f, allow_unicode=True)
    return {"ok": True, "name": name, "autostart": bool(enabled), "critical": tool["critical"]}


def autostart_boot():
    """supervisor 启动钩子：拉起标记自启但已停止的 docker 组件（FR-MGR-022）"""
    from .db import audit
    for t in load_tools():
        if not (t["autostart"] and t["driver"] == "docker" and t.get("container")):
            continue
        try:
            c = _client().containers.get(t["container"])
            if c.status != "running":
                c.start()
                audit("supervisor", "tool.autostart", t["name"])
        except docker.errors.NotFound:
            continue  # 未部署（profile 未启用）跳过
        except docker.errors.DockerException as e:
            audit("supervisor", "tool.autostart_failed", t["name"], str(e)[:200])


# ---------- 状态 / 启停 / 日志 / 详情 ----------

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
        out.append({**{k: v for k, v in t.items()},
                    "status": container_status(t.get("container"))})
    return out


def _get_container(tool: dict):
    container = tool.get("container")
    if not container or tool["driver"] != "docker":
        raise HTTPException(status_code=400, detail="该组件不由 docker 管理")
    try:
        return _client().containers.get(container)
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="容器未部署（对应 profile 未启用）")


def control_tool(name: str, action: str) -> dict:
    c = _get_container(get_tool(name))
    if action == "start":
        c.start()
    elif action == "stop":
        c.stop(timeout=10)
    elif action == "restart":
        c.restart(timeout=10)
    else:
        raise HTTPException(status_code=400, detail="不支持的操作")
    return {"ok": True, "name": name, "action": action}


def tool_logs(name: str, tail: int = 300) -> str:
    c = _get_container(get_tool(name))
    tail = max(1, min(tail, 2000))
    return c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")


def tool_detail(name: str) -> dict:
    tool = get_tool(name)
    info = {**tool}
    info["status"] = container_status(tool.get("container"))
    if tool["driver"] == "docker" and info["status"] not in ("absent", "unknown"):
        c = _get_container(tool)
        state = c.attrs["State"]
        started = state.get("StartedAt", "")
        uptime_sec = None
        if state.get("Running") and started:
            try:
                from datetime import datetime, timezone
                t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
                uptime_sec = int((datetime.now(timezone.utc) - t0).total_seconds())
            except ValueError:
                pass
        info["detail"] = {
            "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:19],
            "started_at": started,
            "uptime_sec": uptime_sec,
            "restart_count": c.attrs.get("RestartCount", 0),
            "health": (state.get("Health") or {}).get("Status"),
            "ports": c.attrs.get("NetworkSettings", {}).get("Ports") or {},
        }
    return info
