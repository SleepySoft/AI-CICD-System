"""注册表加载：harness（ADR-0021 命令模板）+ components（FR-MGR-018）+ prompts

覆盖机制（FR-MGR-020 的全局默认侧）：DATA 目录下的同名文件优先于包内置文件，
用户无需改仓库即可调整配置。
"""
import hashlib
import os
import re

import yaml
from fastapi import HTTPException

from .config import PKG_ROOT, Cfg

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


def skill_path(name: str) -> str | None:
    """组件的 SKILL.md 路径（用户覆盖目录优先）；不存在返回 None（ADR-0025：存在即注入）"""
    for base in (Cfg.DATA / "components" / name, PKG_ROOT / "components" / name):
        p = base / "SKILL.md"
        if p.is_file():
            return str(p)
    return None


def load_components() -> dict:
    """组件配置改从组件插件目录取（ADR-0027）：enabled/url/note 来自 plugin.yaml"""
    from .tools import load_tools
    return {t["name"]: {"enabled": bool(t.get("enabled")), "url": t.get("url", ""),
                        "note": t.get("note", t.get("desc", ""))}
            for t in load_tools()}


def injectable_components() -> list[dict]:
    """可注入 prompt 的组件（ADR-0024/0025）：已启用 且 有 SKILL.md，返回 L0 摘要信息"""
    from .tools import load_tools
    out = []
    for t in load_tools():
        skill = skill_path(t["name"])
        if t.get("enabled") and skill:
            out.append({"name": t["name"], "group": t.get("group", ""),
                        "desc": t.get("note") or t.get("desc", ""), "skill": skill})
    return out


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


def save_prompt_override(task_type: str, content: str) -> dict:
    """保存 prompt 覆盖到 DATA/prompts/（FR-MGR-011：内置模板只读，编辑即覆盖副本）"""
    if not (Cfg.PROMPTS_DIR / f"{task_type}.md").is_file() and \
       not (Cfg.prompts_override_dir() / f"{task_type}.md").is_file():
        raise HTTPException(status_code=404, detail=f"未知任务类型：{task_type}")
    Cfg.prompts_override_dir().mkdir(parents=True, exist_ok=True)
    out = Cfg.prompts_override_dir() / f"{task_type}.md"
    out.write_text(content, encoding="utf-8", newline="\n")
    return {"ok": True, "version": hashlib.sha1(content.encode()).hexdigest()[:8], "path": str(out)}


def delete_prompt_override(task_type: str) -> dict:
    """删除覆盖，回落内置模板"""
    p = Cfg.prompts_override_dir() / f"{task_type}.md"
    if p.is_file():
        p.unlink()
    return {"ok": True}
