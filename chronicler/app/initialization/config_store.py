"""初始化配置与短期秘密暂存；秘密不写草稿、计划、事件或日志。"""
import os
import re
import tempfile
import threading
from pathlib import Path

from ..runtime import PROFILE

_secrets: dict[str, str] = {}
_reveal_consumed = False
_reveal_lock = threading.Lock()
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
GLOBAL_KEYS = {"TZ", "BASE_DOMAIN", "DATA_ROOT", "CHRONICLER_SECRET",
               "CHRONICLER_AUTH_BACKEND", "CHRONICLER_OIDC_SECRET"}
GLOBAL_SECRET_KEYS = {"CHRONICLER_SECRET"}
GLOBAL_VALUE_KEYS = GLOBAL_KEYS - GLOBAL_SECRET_KEYS - {"CHRONICLER_OIDC_SECRET"}


def set_secrets(values: dict[str, str]):
    for key, value in values.items():
        if not KEY.fullmatch(key):
            raise ValueError(f"非法秘密配置键：{key}")
        if any(char in str(value) for char in ("\r", "\n", "\0")):
            raise ValueError(f"秘密配置不得包含换行或空字符：{key}")
        if value:
            _secrets[key] = str(value)


def presence() -> dict[str, bool]:
    return {key: True for key in _secrets}


def configured_presence(components: dict) -> dict[str, bool]:
    """返回当前进程或现有 .env 中可用的秘密，不信任持久草稿中的旧 presence。"""
    result = presence()
    target = PROFILE.install_root / ".env"
    if target.is_file():
        secret_keys = GLOBAL_SECRET_KEYS | {field["key"] for entry in components.values()
                       for field in entry.get("component", {}).get("fields", [])
                       if field.get("kind") == "secret"}
        for line in target.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#") and "=" in clean:
                key, _, value = clean.partition("=")
                if key.strip() in secret_keys and value.strip() and "change_me" not in value.lower():
                    result[key.strip()] = True
    return result


def get_secret(key: str) -> str:
    return _secrets.get(key, "")


def reveal_once(keys: set[str]) -> dict[str, str]:
    """一次性返回本进程中新输入的指定秘密；持久化秘密永不反向读取。"""
    global _reveal_consumed
    with _reveal_lock:
        if _reveal_consumed:
            raise ValueError("本次初始化的凭据导出机会已使用，不能再次显示或导出")
        result = {key: _secrets[key] for key in keys if _secrets.get(key)}
        if not result:
            raise ValueError("没有可导出的新凭据；已有 .env 中的秘密不会被反向读取")
        _reveal_consumed = True
        return result


def redact(value: object) -> str:
    """移除当前进程已登记的秘密，避免 hook/容器异常写入事件与诊断。"""
    text = str(value)
    for secret in sorted((x for x in _secrets.values() if x), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def consume_admin() -> tuple[str, str]:
    return _secrets.get("INIT_ADMIN_USERNAME", "admin"), _secrets.get("INIT_ADMIN_PASSWORD", "")


def allowed_keys(components: dict) -> set[str]:
    keys = set(GLOBAL_KEYS)
    for entry in components.values():
        for field in entry.get("component", {}).get("fields", []):
            keys.add(field["key"])
    return keys


def _parse(path: Path) -> tuple[list[str], dict[str, int]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    indexes = {}
    for i, line in enumerate(lines):
        clean = line.strip()
        if clean and not clean.startswith("#") and "=" in clean:
            indexes[clean.partition("=")[0].strip()] = i
    return lines, indexes


def load_environment(components: dict):
    """把已持久化的白名单配置载入当前进程，供重试和中断续接使用。"""
    target = PROFILE.install_root / ".env"
    if not target.is_file():
        return
    allowed = allowed_keys(components)
    for line in target.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#") and "=" in clean:
            key, _, value = clean.partition("=")
            if key.strip() in allowed:
                os.environ[key.strip()] = value.strip()


def persist(values: dict, components: dict) -> Path:
    """合并 .env.example/.env，保留未知键和注释，同目录原子替换。"""
    target = PROFILE.install_root / ".env"
    source = target if target.is_file() else PROFILE.install_root / ".env.example"
    lines, indexes = _parse(source)
    updates = {k: str(v) for k, v in values.items() if k in allowed_keys(components) and v is not None}
    updates.update({k: v for k, v in _secrets.items()
                    if k in allowed_keys(components) and not k.startswith("INIT_ADMIN_")})
    invalid = [key for key, value in updates.items() if any(char in value for char in ("\r", "\n", "\0"))]
    if invalid:
        raise ValueError("配置值不得包含换行或空字符：" + "、".join(sorted(invalid)))
    for key, value in sorted(updates.items()):
        line = f"{key}={value}"
        if key in indexes:
            lines[indexes[key]] = line
        else:
            lines.append(line)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".env.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines).rstrip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    for key, value in updates.items():
        os.environ[key] = value
    load_environment(components)
    return target


def clear():
    global _reveal_consumed
    with _reveal_lock:
        _secrets.clear()
        _reveal_consumed = False