"""组件能力脚本的通用执行器（ADR-0027 扩展）。

能力即文件存在（ADR-0025）：组件在自身 hooks/ 下提供 <能力>.py 即声明该能力，
核心按约定发现、注入环境并调用——不含任何组件名、字段、端口或接线知识。

脚本约定：python hooks/<能力>.py <args...>；stdout 末行输出 JSON（至少含 ok）。
环境注入：基础键 + 该组件依赖闭包在 setup.yaml 自述的全部字段（糊化 VAULT: 引用
从秘密库解析真实值）+ 容器名变量。
"""
import json
import os
import subprocess
from pathlib import Path

from .config import Cfg
from .runtime import PROFILE, component_python

_BASE_KEYS = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP",
              "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY",
              "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "BASE_DOMAIN"}


def find_capability(script: str) -> str | None:
    """返回提供 hooks/<script> 的组件名；多个提供者按名取序首个。"""
    base = Cfg.COMPONENTS_DIR
    if not base.is_dir():
        return None
    for child in sorted(base.iterdir()):
        if (child / "hooks" / script).is_file():
            return child.name
    return None


def run_capability(script: str, args: list[str], timeout: int = 120,
                   env: dict[str, str] | None = None) -> dict | None:
    """执行提供该能力的组件脚本；无提供者返回 None。"""
    name = find_capability(script)
    if not name:
        return None
    path = Cfg.COMPONENTS_DIR / name / "hooks" / script
    capability_env = _capability_env(name)
    if env:
        capability_env.update(env)
    proc = subprocess.run([component_python(), str(path), *args],
                          cwd=str(path.parent.parent), env=capability_env,
                          capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    lines = (proc.stdout or "").strip().splitlines()
    result = {}
    if lines:
        try:
            result = json.loads(lines[-1])
        except json.JSONDecodeError:
            result = {}
    if proc.returncode != 0:
        result.setdefault("ok", False)
        result.setdefault("error", (proc.stderr or "").strip()[-300:] or f"exit {proc.returncode}")
    else:
        result.setdefault("ok", True)
        # 账号/客户端类能力成功 = 该组件秘密已直写对齐，消除「待传播」横幅标记
        if script in ("users.py", "oidc.py"):
            try:
                from .vault import store as vault_store
                vault_store.clear_pending(name, actor="capability")
            except Exception:
                pass
    return result


def _capability_env(name: str) -> dict:
    """注入环境：基础键 + 依赖闭包自述字段（VAULT: 引用从秘密库解析）+ 容器名。"""
    from .initialization import catalog
    entries = catalog.load()
    closure, queue = {name}, [name]
    while queue:
        current = queue.pop()
        for dep in entries.get(current, {}).get("component", {}).get("depends_on", []):
            if dep not in closure and dep in entries:
                closure.add(dep)
                queue.append(dep)
    field_keys = {field["key"] for comp in closure
                  for field in entries.get(comp, {}).get("component", {}).get("fields", [])}
    env = {key: value for key, value in os.environ.items() if key.upper() in _BASE_KEYS}
    env.update(_resolved_field_env(field_keys))
    from .tools import get_tool
    env["CHRONICLER_COMPONENT_CONTAINER"] = get_tool(name).get("container", "")
    for dep in closure - {name}:
        env[f"CHRONICLER_DEPENDENCY_{dep.upper().replace('-', '_')}_CONTAINER"] = \
            get_tool(dep).get("container", "")
    return env


def _resolved_field_env(field_keys: set) -> dict:
    """从糊化 .env 解析自述字段（VAULT: 引用经秘密库取真实值）；未配置/解析失败的键跳过。"""
    from .vault import sync as vault_sync
    path = PROFILE.install_root / ".env"
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, _, value = clean.partition("=")
        key, value = key.strip(), value.strip()
        if key not in field_keys:
            continue
        if value.startswith(vault_sync.VAULT_PREFIX):
            try:
                value = vault_sync.resolve_ref(value[len(vault_sync.VAULT_PREFIX):])
            except Exception:  # noqa: BLE001 锁定/缺条目：跳过该键
                continue
        if value and "change_me" not in value.lower():
            out[key] = value
    return out
