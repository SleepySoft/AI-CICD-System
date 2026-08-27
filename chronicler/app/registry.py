"""注册表加载：harness（ADR-0021 命令模板）+ components（FR-MGR-018）+ prompts

覆盖机制（FR-MGR-020 的全局默认侧）：DATA 目录下的同名文件优先于包内置文件，
用户无需改仓库即可调整配置。
"""
import hashlib
import os
import re

import yaml
from fastapi import HTTPException

from .config import Cfg

_ENV_REF = re.compile(r"^\$\{(\w+)\}$")


def _load_yaml(name: str, key: str) -> list | dict:
    """优先读 DATA 覆盖目录，其次包内置 config/。"""
    override = Cfg.DATA / "config" / name
    path = override if override.is_file() else Cfg.CONFIG_DIR / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)[key]


def load_harnesses() -> list[dict]:
    return _load_yaml("harness.yaml", "harnesses")


def get_harness(name: str) -> dict:
    h = next((x for x in load_harnesses() if x["name"] == name), None)
    if not h:
        raise HTTPException(status_code=404, detail=f"未知 harness：{name}")
    return h


def load_components() -> dict:
    return _load_yaml("components.yaml", "components")


def enabled_components() -> dict:
    return {k: v for k, v in load_components().items() if v.get("enabled")}


def resolve_env(env_spec: dict | None) -> dict[str, str]:
    """注册表 env 中的 ${VAR} 从 supervisor 进程环境解析；空值丢弃（NFR-002）"""
    out = {}
    for k, v in (env_spec or {}).items():
        m = _ENV_REF.match(str(v))
        value = os.environ.get(m.group(1), "") if m else str(v)
        if value:
            out[k] = value
    return out


def load_prompt(task_type: str) -> tuple[str, str]:
    """返回 (内容, 版本hash)。DATA/prompts 覆盖优先（FR-MGR-011 版本=内容 hash）"""
    name = f"{task_type}.md"
    override = Cfg.prompts_override_dir() / name
    path = override if override.is_file() else Cfg.PROMPTS_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"未知任务类型：{task_type}（缺少 prompt 模板 {name}）")
    content = path.read_text(encoding="utf-8")
    return content, hashlib.sha1(content.encode()).hexdigest()[:8]
