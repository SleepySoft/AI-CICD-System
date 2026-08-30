"""全局配置查看路由（FR-MGR-018/019）：注册表只读展示 + prompt 模板读写

配置本体是 YAML 文件（热更新），YAML 不提供写操作——改文件即生效（ADR-0018 模式）。
prompt 模板例外：内置只读，编辑写覆盖副本（FR-MGR-011）。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import registry
from ..auth import current_user, require_admin
from ..config import Cfg

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/harnesses")
async def harnesses(user: dict = Depends(current_user)):
    # env 中的 ${VAR} 引用只回传引用名，绝不回传解析后的密钥明文（NFR-002）
    return [{"name": h["name"], "desc": h.get("desc", ""),
             "command_template": h["command_template"], "session": h.get("session", "once"),
             "timeout_sec": h.get("timeout_sec", 1800),
             "env_keys": list((h.get("env") or {}).keys())} for h in registry.load_harnesses()]


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
    from ..db import audit
    audit(user["username"], "prompt.save", name, r["version"])
    return r


@router.delete("/prompts/{name}/override")
async def prompt_reset(name: str, user: dict = Depends(require_admin)):
    return registry.delete_prompt_override(name)
