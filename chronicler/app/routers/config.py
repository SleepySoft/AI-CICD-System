"""全局配置路由（FR-MGR-018/019/020）：harness/settings 读写 + prompt 模板读写

配置本体是 YAML 文件（热更新），YAML 不提供写操作——改文件即生效（ADR-0018 模式）。
页面写操作（admin）均落到 DATA 覆盖副本：prompt 覆盖（FR-MGR-011）、
settings.yaml（默认 harness）、harness.yaml（整表）。内置文件保持只读。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import registry
from ..auth import current_user, require_admin
from ..config import Cfg
from ..db import audit

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/harnesses")
async def harnesses(user: dict = Depends(current_user)):
    # env 中的 ${VAR} 引用只回传引用名，绝不回传解析后的密钥明文（NFR-002）
    return [{"name": h["name"], "desc": h.get("desc", ""),
             "command_template": h["command_template"], "session": h.get("session", "once"),
             "timeout_sec": h.get("timeout_sec", 1800),
             "stdin_prompt": bool(h.get("stdin_prompt")),
             "report_mode": h.get("report_mode", "file"),
             "cwd": h.get("cwd", "repo"),
             "env_keys": list((h.get("env") or {}).keys())} for h in registry.load_harnesses()]


class SettingsBody(BaseModel):
    default_harness: str
    default_publish_policy: str = "direct"


@router.get("/settings")
async def settings(user: dict = Depends(current_user)):
    return {"default_harness": registry.get_default_harness(),
            "harness_names": [h["name"] for h in registry.load_harnesses()],
            "default_publish_policy": registry.get_publish_policy(),
            "publish_policies": list(registry.PUBLISH_POLICIES)}


@router.put("/settings")
async def settings_save(body: SettingsBody, user: dict = Depends(require_admin)):
    name = body.default_harness.strip()
    if name not in {h["name"] for h in registry.load_harnesses()}:
        raise HTTPException(status_code=422, detail=f"未知 harness：{name}")
    policy = body.default_publish_policy.strip()
    if policy not in registry.PUBLISH_POLICIES:
        raise HTTPException(status_code=422, detail=f"尚未支持的发布策略：{policy}")
    merged = registry.load_settings()
    merged["default_harness"] = name
    merged["default_publish_policy"] = policy
    r = registry.save_settings(merged)
    audit(user["username"], "config.defaults", f"harness={name}, publish={policy}")
    return {"ok": True, "default_harness": name,
            "default_publish_policy": policy, "path": r["path"]}


class HarnessBody(BaseModel):
    name: str
    desc: str = ""
    command_template: str
    session: str = "once"
    stdin_prompt: bool = False
    report_mode: str = "file"
    cwd: str = "repo"
    env: dict = {}
    timeout_sec: int = 1800


@router.post("/harnesses")
async def harness_upsert(body: HarnessBody, user: dict = Depends(require_admin)):
    """新增/更新一条 harness（写入 DATA 覆盖 harness.yaml 整表）"""
    merged = registry.load_harnesses()
    entry = body.model_dump()
    # env 值留空 = 保持原值（编辑时密钥不回显，NFR-002）；整行删除 = 移除该键
    existing = next((h for h in merged if h["name"] == entry["name"]), None)
    if existing:
        old_env = existing.get("env") or {}
        entry["env"] = {k: (v if v != "" else old_env.get(k, ""))
                        for k, v in (entry["env"] or {}).items()}
    merged = [h for h in merged if h["name"] != entry["name"]] + [entry]
    r = registry.save_harnesses(merged)
    audit(user["username"], "config.harness.save", entry["name"])
    return {"ok": True, "path": r["path"], "count": r["count"]}


@router.delete("/harnesses/{name}")
async def harness_delete(name: str, user: dict = Depends(require_admin)):
    merged = registry.load_harnesses()
    if name not in {h["name"] for h in merged}:
        raise HTTPException(status_code=404, detail=f"未知 harness：{name}")
    rest = [h for h in merged if h["name"] != name]
    if not rest:
        raise HTTPException(status_code=422, detail="至少保留一个 harness")
    r = registry.save_harnesses(rest)
    audit(user["username"], "config.harness.delete", name)
    return {"ok": True, "path": r["path"], "count": r["count"]}


@router.get("/components")
async def components(user: dict = Depends(current_user)):
    return registry.load_components()


@router.get("/prompts")
async def prompts(user: dict = Depends(current_user)):
    out = []
    for path in sorted(Cfg.PROMPTS_DIR.glob("*.md")):
        content, version = registry.load_prompt(path.stem)
        out.append({"task_type": path.stem, "version": version,
                    "overridden": (Cfg.prompts_override_dir() / path.name).is_file(),
                    "size": len(content)})
    return out


@router.get("/prompts/{name}/content")
async def prompt_content(name: str, user: dict = Depends(current_user)):
    content, version = registry.load_prompt(name)
    return {"task_type": name, "version": version, "content": content,
            "overridden": (Cfg.prompts_override_dir() / f"{name}.md").is_file()}


class PromptBody(BaseModel):
    content: str


@router.put("/prompts/{name}")
async def prompt_save(name: str, body: PromptBody, user: dict = Depends(require_admin)):
    r = registry.save_prompt_override(name, body.content)
    audit(user["username"], "prompt.save", name, r["version"])
    return r


@router.delete("/prompts/{name}/override")
async def prompt_reset(name: str, user: dict = Depends(require_admin)):
    return registry.delete_prompt_override(name)
