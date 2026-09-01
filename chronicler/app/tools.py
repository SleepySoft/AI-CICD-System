"""组件插件注册与生命周期管理（FR-MGR-001 状态/启停 + FR-MGR-022 自启/日志/详情/插件化）

插件化：chronicler/config/tools.d/*.yaml 一个文件一个组件；
data/chronicler/config/tools.d/*.yaml 为用户目录（同名覆盖内置）。
自启开关持久化在 data/chronicler/config/autostart.yaml（运行时覆盖层）。
docker 控制走本地 socket（ADR-0020：supervisor 与 dockerd 同环境）。
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import docker
import yaml
from fastapi import HTTPException

from .config import PKG_ROOT, Cfg

_docker = None


def _client() -> docker.DockerClient:
    global _docker
    if _docker is None:
        _docker = docker.from_env()
    return _docker


def _load_plugins_dir(d) -> dict:
    """扫描组件目录：<d>/<name>/plugin.yaml（ADR-0027 组件目录自包含）"""
    out = {}
    if d.is_dir():
        for child in sorted(d.iterdir()):
            f = child / "plugin.yaml"
            if child.is_dir() and f.is_file():
                with open(f, encoding="utf-8") as fh:
                    entry = yaml.safe_load(fh)
                if entry and entry.get("name"):
                    entry["_dir"] = str(child)
                    out[entry["name"]] = entry
    return out


def load_tools() -> list[dict]:
    """合并 内置 components/ + 用户 components/ + autostart 覆盖层，字段归一化"""
    merged = _load_plugins_dir(PKG_ROOT / "components")
    merged.update(_load_plugins_dir(Cfg.DATA / "components"))
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


# ---------- 自启开关与启动拉起 ----------

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


def _compose_up_cmd(tool: dict) -> tuple[list, dict]:
    """构造组件 compose 拉起命令（args, env）；调用方负责网络先备（_ensure_network）"""
    compose_file = Path(tool["_dir"]) / "compose.yml"
    if not compose_file.is_file():
        raise HTTPException(status_code=400, detail=f"组件无部署定义（缺 compose.yml）")
    env = {**os.environ,
           "REPO_ROOT": str(PKG_ROOT.parent),
           "DATA_ROOT": str(PKG_ROOT.parent / "data")}
    service = tool.get("compose_service") or tool["name"]
    return (["docker", "compose", "-p", "aisystem", "--env-file", str(PKG_ROOT.parent / ".env"),
             "-f", str(compose_file), "up", "-d", service], env)


def _ensure_network():
    try:
        _client().networks.get("aisystem")
    except docker.errors.NotFound:
        _client().networks.create("aisystem", driver="bridge")


def _compose_up(tool: dict) -> subprocess.CompletedProcess:
    """按组件 compose 文件拉起（ADR-0027：部署定义在组件目录）"""
    _ensure_network()
    args, env = _compose_up_cmd(tool)
    return subprocess.run(args, env=env, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=900)


def ensure_running(tool: dict) -> str:
    """确保组件运行：running→跳过；stopped→docker start；absent→compose up -d 现场创建
    返回动作：skip/start/compose-up/error"""
    import subprocess
    from .db import audit
    name, container = tool["name"], tool.get("container")
    if tool["driver"] != "docker" or not container:
        return "skip"
    try:
        c = _client().containers.get(container)
        if c.status == "running":
            return "skip"
        c.start()
        audit("supervisor", "tool.autostart", name)
        return "start"
    except docker.errors.NotFound:
        # 组件自带部署钩子则优先（ADR-0027）；否则回落 docker compose
        hook = Path(tool["_dir"]) / "hooks" / "deploy.py" if tool.get("_dir") else None
        if hook and hook.is_file():
            r = subprocess.run([sys.executable, str(hook), "up"],
                               cwd=str(PKG_ROOT.parent), capture_output=True,
                               encoding="utf-8", errors="replace", timeout=600)
            if r.returncode == 0:
                audit("supervisor", "tool.deploy_hook", name)
                return "deploy-hook"
            audit("supervisor", "tool.autostart_failed", name, r.stderr.strip()[:200])
            return "error"
        service = tool.get("compose_service") or name
        try:
            r = _compose_up(tool)
            if r.returncode == 0:
                audit("supervisor", "tool.autostart_compose", name)
                return "compose-up"
            audit("supervisor", "tool.autostart_failed", name, r.stderr.strip()[:200])
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            audit("supervisor", "tool.autostart_failed", name, str(e)[:200])
        return "error"
    except docker.errors.DockerException as e:
        audit("supervisor", "tool.autostart_failed", name, str(e)[:200])
        return "error"


def autostart_boot(max_wait_sec: int = 600, interval: int = 20):
    """supervisor 启动钩子（后台线程）：拉起所有标记自启的组件（FR-MGR-022）
    dockerd 未就绪（如 Docker Desktop 未启动/启动慢）时每 20s 重试至多 10 分钟，
    而不是一次性放弃——supervisor 通常比 dockerd 先活。"""
    env_file = PKG_ROOT.parent / ".env"
    if not env_file.is_file():
        print(f"[ERROR] autostart 跳过：缺少首要依赖 {env_file}（请先 cp .env.example .env 并编辑 *_change_me）",
              file=sys.stderr)
        return
    deadline = time.time() + max_wait_sec
    while True:
        try:
            _client().ping()
            break
        except docker.errors.DockerException:
            if time.time() > deadline:
                return
            time.sleep(interval)
    for t in load_tools():
        if t["autostart"]:
            ensure_running(t)


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
    tool = get_tool(name)
    if action == "deploy":
        start_deploy(tool)  # 异步：前端轮询 deploy-log 看实时进度
        return {"ok": True, "name": name, "action": action, "via": "async"}
    c = _get_container(tool)
    if action == "start":
        c.start()
    elif action == "stop":
        c.stop(timeout=10)
    elif action == "restart":
        c.restart(timeout=10)
    else:
        raise HTTPException(status_code=400, detail="不支持的操作")
    return {"ok": True, "name": name, "action": action}


# ---------- 异步部署（实时进度） ----------

_deploy_tasks: dict = {}
_deploy_lock = threading.Lock()


def start_deploy(tool: dict):
    """后台线程执行 compose up -d，输出行实时收集供前端轮询"""
    name = tool["name"]
    with _deploy_lock:
        task = _deploy_tasks.get(name)
        if task and task["state"] == "running":
            raise HTTPException(status_code=409, detail="该组件正在部署中")
        _deploy_tasks[name] = {"state": "running", "lines": []}
    threading.Thread(target=_deploy_worker, args=(tool,), daemon=True).start()


def _deploy_worker(tool: dict):
    import subprocess as sp
    name = tool["name"]
    task = _deploy_tasks[name]

    def emit(line: str):
        task["lines"].append(line)
        del task["lines"][:-200]  # 只保留最近 200 行

    emit(f"$ compose up（组件定义 {Path(tool['_dir']).name}/compose.yml）")
    try:
        _ensure_network()
        args, env = _compose_up_cmd(tool)
        proc = sp.Popen(args, env=env, stdout=sp.PIPE, stderr=sp.STDOUT,
                        encoding="utf-8", errors="replace")
        for line in proc.stdout:
            emit(line.rstrip())
        proc.wait(timeout=900)
        if proc.returncode == 0:
            emit("✔ 部署完成")
            task["state"] = "done"
            from .db import audit
            audit("supervisor", "tool.deploy", name)
        else:
            emit(f"✘ 部署失败（exit {proc.returncode}）")
            task["state"] = "error"
    except Exception as e:  # noqa: BLE001 - 部署线程兜底
        emit(f"✘ {type(e).__name__}: {e}")
        task["state"] = "error"


def deploy_status(name: str) -> dict:
    task = _deploy_tasks.get(name)
    if not task:
        return {"state": "idle", "lines": []}
    return {"state": task["state"], "lines": task["lines"]}


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
