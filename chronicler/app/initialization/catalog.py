"""组件 setup.yaml 目录与契约校验。"""
import hashlib
import json
import platform
import re
from pathlib import Path

import yaml

from ..config import Cfg

KINDS = {"text", "secret", "integer", "boolean", "choice", "path", "port"}
READINESS = {"container-health", "http", "tcp", "process"}
SECRET_TYPES = {"password", "client-secret", "encryption-key", "api-token", "access-key"}
ROTATION_RISKS = {"low", "coordinated", "critical"}
SENSITIVE = re.compile(r"(?i)(secret|password|token|api_?key|credential)")
ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class CatalogError(ValueError):
    pass


def validate(name: str, raw: dict, component_dir: Path) -> dict:
    if raw.get("schema_version") != 1:
        raise CatalogError("不支持的 schema_version")
    fields = raw.get("fields") or []
    seen = set()
    for field in fields:
        key, kind = field.get("key", ""), field.get("kind", "text")
        if not ENV_KEY.fullmatch(key) or key in seen:
            raise CatalogError(f"非法或重复配置键：{key}")
        if kind not in KINDS:
            raise CatalogError(f"不支持的字段类型：{kind}")
        summary = field.get("summary")
        if summary not in (None, "account"):
            raise CatalogError(f"不支持的字段 summary：{key}")
        if summary == "account" and kind == "secret":
            raise CatalogError(f"账号摘要字段不得声明为 secret：{key}")
        if SENSITIVE.search(key) and kind != "secret":
            raise CatalogError(f"敏感字段必须声明 kind=secret：{key}")
        if kind == "secret" and field.get("default"):
            raise CatalogError(f"秘密字段不得包含默认值：{key}")
        if kind == "secret":
            if field.get("secret_type") not in SECRET_TYPES:
                raise CatalogError(f"秘密字段必须声明有效 secret_type：{key}")
            if field.get("rotation_risk") not in ROTATION_RISKS:
                raise CatalogError(f"秘密字段必须声明有效 rotation_risk：{key}")
            length = field.get("generate_length")
            if not isinstance(length, int) or not 16 <= length <= 128:
                raise CatalogError(f"秘密字段 generate_length 必须在 16-128：{key}")
            if not str(field.get("help", "")).strip():
                raise CatalogError(f"秘密字段必须提供用途和轮换说明：{key}")
        seen.add(key)
    readiness = raw.get("readiness") or {}
    if readiness and readiness.get("kind") not in READINESS:
        raise CatalogError("不支持的 readiness.kind")
    hook = raw.get("initialize_hook")
    if hook:
        target = (component_dir / hook).resolve()
        if component_dir.resolve() not in target.parents:
            raise CatalogError("initialize_hook 不得越出组件目录")
    dependency_only = raw.get("dependency_only", False)
    if not isinstance(dependency_only, bool):
        raise CatalogError("dependency_only 必须是布尔值")
    return {"name": name, "profiles": raw.get("profiles") or [],
            "depends_on": raw.get("depends_on") or [],
            "conflicts_with": raw.get("conflicts_with") or [],
            "platforms": raw.get("platforms") or ["windows", "linux", "darwin"],
            "resources": raw.get("resources") or {}, "fields": fields,
            "readiness": readiness, "initialize_hook": hook or "",
            "dependency_only": dependency_only,
            "_dir": str(component_dir)}


def load() -> dict:
    result = {}
    for base in (Cfg.COMPONENTS_DIR, Cfg.DATA / "components"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            path = child / "setup.yaml"
            if not path.is_file():
                continue
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                plugin_path = child / "plugin.yaml"
                plugin = yaml.safe_load(plugin_path.read_text(encoding="utf-8")) or {} if plugin_path.is_file() else {}
                presentation = {"group": plugin.get("group") or "其他",
                                "description": plugin.get("desc") or child.name}
                result[child.name] = {"component": validate(child.name, raw, child),
                                      "presentation": presentation, "error": ""}
            except (OSError, yaml.YAMLError, CatalogError) as exc:
                result[child.name] = {"component": {"name": child.name}, "error": str(exc)}
    return result


def revision(items: dict) -> str:
    safe = {}
    for name, entry in items.items():
        component = {k: v for k, v in entry.get("component", {}).items() if k != "_dir"}
        safe[name] = {"component": component, "error": entry.get("error", "")}
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()


def current_platform() -> str:
    return {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system(), "unknown")


def public_catalog() -> dict:
    entries = load()
    components = []
    for name, entry in entries.items():
        component = dict(entry["component"])
        component.pop("_dir", None)
        components.append({**component, **entry.get("presentation", {}), "error": entry["error"]})
    return {"schema_version": 1, "revision": revision(entries),
            "platform": current_platform(), "profiles": ["chronicler-only", "recommended", "full", "custom"],
            "components": components}