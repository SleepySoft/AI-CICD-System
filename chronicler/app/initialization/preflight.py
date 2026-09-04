"""初始化环境预检：目录、Docker/Compose、组件声明与计划端口。"""
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import docker

from ..config import Cfg
from ..runtime import PROFILE
from ..tools import get_tool
from . import catalog, planner


def _check_dir(name: str, path: Path) -> dict:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".chronicler-write-", dir=path, delete=True):
            pass
        return {"name": name, "status": "pass", "message": f"可写：{path}"}
    except OSError as exc:
        return {"name": name, "status": "block", "message": f"不可写：{path}；请检查目录权限（{exc}）"}


def _selected(draft: dict, entries: dict) -> set[str]:
    try:
        return planner._selected(draft["profile"], draft["selections"], entries)[0]
    except planner.PlanError:
        return set()


def _port_owner(port: int) -> str:
    try:
        for container in docker.from_env().containers.list(all=True):
            for bindings in (container.attrs.get("NetworkSettings", {}).get("Ports") or {}).values():
                if any(int(binding.get("HostPort", 0)) == port for binding in bindings or []):
                    return container.name
    except Exception:
        pass
    return ""


def port_checks(draft: dict, entries: dict | None = None) -> list[dict]:
    entries = entries or catalog.load()
    selected = _selected(draft, entries)
    targets: dict[int, str] = {}
    for name in selected:
        for field in entries[name]["component"].get("fields", []):
            if field.get("kind") != "port":
                continue
            value = draft["values"].get(field["key"], field.get("default"))
            if value not in (None, ""):
                targets[int(value)] = name

    checks = []
    for port, component in sorted(targets.items()):
        if not 1 <= port <= 65535:
            checks.append({"name": f"端口 {port}", "status": "block", "message": "端口必须在 1-65535 范围内"})
            continue
        owner = _port_owner(port)
        expected = get_tool(component).get("container", "")
        if owner and owner == expected:
            checks.append({"name": f"端口 {port}", "status": "pass", "message": f"已由目标组件 {component} 使用，将复用"})
            continue
        sock = socket.socket()
        try:
            sock.settimeout(0.2)
            sock.bind(("0.0.0.0", port))
            checks.append({"name": f"端口 {port}", "status": "pass", "message": f"可供 {component} 使用"})
        except OSError as exc:
            detail = f"，当前 Docker 容器：{owner}" if owner else ""
            checks.append({"name": f"端口 {port}", "status": "block",
                           "message": f"无法绑定，请释放或修改端口{detail}（{exc}）"})
        finally:
            sock.close()
    return checks


def run(draft: dict, require_docker: bool = False, check_ports: bool = False) -> dict:
    checks = []
    try:
        client = docker.from_env()
        version = client.version().get("Version", "unknown")
        checks.append({"name": "Docker", "status": "pass", "message": f"Docker {version} 可用"})
    except Exception as exc:
        checks.append({"name": "Docker", "status": "block" if require_docker else "warn",
                       "message": f"Docker 不可用；请启动 Docker Desktop 或 dockerd 后重试（{exc}）"})

    executable = shutil.which("docker")
    if executable:
        try:
            result = subprocess.run([executable, "compose", "version", "--short"], capture_output=True,
                                    encoding="utf-8", errors="replace", timeout=15)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip())
            checks.append({"name": "Docker Compose", "status": "pass",
                           "message": f"Compose {result.stdout.strip()} 可用"})
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            checks.append({"name": "Docker Compose", "status": "block" if require_docker else "warn",
                           "message": f"Compose 不可用；请安装 Docker Compose v2（{exc}）"})
    else:
        checks.append({"name": "Docker Compose", "status": "block" if require_docker else "warn",
                       "message": "找不到 docker 命令；请安装 Docker Desktop 或 Docker Engine + Compose v2"})

    checks.extend((_check_dir("安装目录", PROFILE.install_root), _check_dir("数据目录", Cfg.DATA)))
    entries = catalog.load()
    invalid = [name for name, entry in entries.items() if entry["error"]]
    checks.append({"name": "组件声明", "status": "block" if invalid else "pass",
                   "message": "无效组件：" + "、".join(invalid) if invalid else f"{len(entries)} 个组件声明有效"})
    if check_ports:
        try:
            checks.extend(port_checks(draft, entries))
        except (TypeError, ValueError) as exc:
            checks.append({"name": "端口配置", "status": "block", "message": f"端口值无效：{exc}"})
    return {"ok": not any(item["status"] == "block" for item in checks), "checks": checks}
