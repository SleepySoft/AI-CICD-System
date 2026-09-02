"""注册表加载：harness（ADR-0021 命令模板）+ components（FR-MGR-018）+ prompts

覆盖机制（FR-MGR-020 的全局默认侧）：DATA 目录下的同名文件优先于包内置文件，
用户无需改仓库即可调整配置。
"""
import hashlib
import os
import re
from pathlib import Path

import yaml
from fastapi import HTTPException

from .config import PKG_ROOT, Cfg

_ENV_REF = re.compile(r"^\$\{(\w+)\}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
PUBLISH_POLICIES = ("direct",)


def _write_data_yaml(name: str, data, header: str = "") -> Path:
    """写 DATA 覆盖文件（LF 行尾；父目录自动创建）"""
    out = Cfg.DATA / "config" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    text = header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


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


def _validate_harness(h: dict) -> dict:
    """harness 条目契约校验（页面增删改与任务执行共用）；返回规范化条目"""
    name = str(h.get("name", "")).strip()
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="name 需为英数/连字符/下划线开头且非空")
    command = str(h.get("command_template", "")).strip()
    if not command:
        raise HTTPException(status_code=422, detail="command_template 不能为空")
    if h.get("session") not in (None, "once", "persistent"):
        raise HTTPException(status_code=422, detail="session 仅支持 once|persistent")
    if h.get("report_mode") not in (None, "file", "stdout"):
        raise HTTPException(status_code=422, detail="report_mode 仅支持 file|stdout")
    if h.get("cwd") not in (None, "repo", "shadow"):
        raise HTTPException(status_code=422, detail="cwd 仅支持 repo|shadow")
    if h.get("env") is not None and not isinstance(h.get("env"), dict):
        raise HTTPException(status_code=422, detail="env 需为键值映射")
    try:
        timeout = int(h.get("timeout_sec", 1800))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="timeout_sec 需为整数")
    if timeout <= 0:
        raise HTTPException(status_code=422, detail="timeout_sec 需为正整数")
    return {
        "name": name,
        "desc": str(h.get("desc", "")).strip(),
        "command_template": command,
        "session": h.get("session") or "once",
        "report_mode": h.get("report_mode") or "file",
        "cwd": h.get("cwd") or "repo",
        "stdin_prompt": bool(h.get("stdin_prompt")),
        "env": dict(h.get("env") or {}),
        "timeout_sec": timeout,
    }


def save_harnesses(harnesses: list) -> dict:
    """写 DATA 覆盖 harness.yaml（整表替换，含内置条目；页面增删改均走此接口）"""
    cleaned = [_validate_harness(h) for h in harnesses]
    if len({h["name"] for h in cleaned}) != len(cleaned):
        raise HTTPException(status_code=422, detail="harness name 重复")
    header = ("# Agent harness 注册表（配置页写入的覆盖文件；data/config 同名文件覆盖包内置）\n"
              "# 字段说明见 chronicler/config/harness.yaml 头注释与 docs/runbooks/agent-onboarding.md\n")
    out = _write_data_yaml("harness.yaml", {"harnesses": cleaned}, header)
    return {"ok": True, "path": str(out), "count": len(cleaned)}


def load_settings() -> dict:
    """全局设置：DATA 覆盖优先，其次包内置 config/settings.yaml"""
    override = Cfg.DATA / "config" / "settings.yaml"
    path = override if override.is_file() else Cfg.CONFIG_DIR / "settings.yaml"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> dict:
    """保存全局设置到 DATA 覆盖文件"""
    if not isinstance(settings, dict):
        raise HTTPException(status_code=422, detail="settings 需为键值映射")
    out = _write_data_yaml("settings.yaml", settings)
    return {"ok": True, "path": str(out)}


def get_default_harness() -> str:
    """全局默认 harness：settings.yaml 优先，其次 CHRONICLER_DEFAULT_HARNESS，最后 dummy"""
    name = str(load_settings().get("default_harness") or
               os.environ.get("CHRONICLER_DEFAULT_HARNESS", "dummy"))
    names = {h["name"] for h in load_harnesses()}
    return name if name in names else "dummy"


def get_publish_policy(project: dict | None = None) -> str:
    """AI 产物发布策略：工程覆盖 > 全局设置；当前首版仅实现 direct。"""
    configured = (project or {}).get("overrides", {}).get("publish_policy")
    policy = str(configured or load_settings().get("default_publish_policy") or "direct")
    return policy if policy in PUBLISH_POLICIES else "direct"


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
