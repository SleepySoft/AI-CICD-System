"""工程路由（FR-MGR-020）：查询全员可用；创建/修改/同步仅 admin"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import projects
from ..auth import current_user, require_admin
from ..db import audit

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectBody(BaseModel):
    name: str
    git_url: str
    default_branch: str = ""
    ci_url: str = ""
    shadow_repo: str = ""
    description: str = ""
    overrides: dict = {}


class ProjectPatch(BaseModel):
    git_url: str | None = None
    default_branch: str | None = None
    ci_url: str | None = None
    shadow_repo: str | None = None
    description: str | None = None
    overrides: dict | None = None


@router.get("")
async def list_(user: dict = Depends(current_user)):
    return projects.list_projects()


@router.post("")
async def create(body: ProjectBody, user: dict = Depends(require_admin)):
    from .. import tasks as task_mod
    p = projects.create_project(body.name, body.git_url, body.ci_url, body.description,
                                body.overrides, body.default_branch, body.shadow_repo)
    task_mod.create_preset_tasks(p["id"])  # 新建工程默认挂预置任务（仅手动触发）
    audit(user["username"], "project.create", body.name)
    return p


@router.get("/{pid}")
async def detail(pid: int, user: dict = Depends(current_user)):
    return projects.get_project(pid)


@router.patch("/{pid}")
async def update(pid: int, body: ProjectPatch, user: dict = Depends(require_admin)):
    p = projects.update_project(pid, body.model_dump(exclude_none=True))
    audit(user["username"], "project.update", p["name"])
    return p


@router.post("/{pid}/reset-clone")
def reset_clone(pid: int, user: dict = Depends(require_admin)):
    result = projects.reset_clone(pid)
    audit(user["username"], "project.reset_clone", projects.get_project(pid)["name"])
    return result


@router.delete("/{pid}")
async def delete(pid: int, user: dict = Depends(require_admin)):
    from .. import tasks
    from .. import maintenance
    p = projects.get_project(pid)
    with projects.project_gate(pid), projects.repo_lock(pid):
        from fastapi import HTTPException
        if projects.q1("SELECT id FROM task_runs WHERE project_id=? AND status IN ('queued','running')",
                       (pid,)):
            raise HTTPException(status_code=409, detail="工程仍有排队或运行中的任务")
        # 先安全删除工作区克隆；报告和 Shadow 保留，供追溯或在清理页单独删除。
        maintenance._remove(projects.Cfg.repos_dir(), str(pid))
        tasks.delete_project_tasks(pid)
        projects.execute("DELETE FROM task_runs WHERE project_id=?", (pid,))
        projects.execute("DELETE FROM projects WHERE id=?", (pid,))
    audit(user["username"], "project.delete", p["name"])
    return {"ok": True}


@router.post("/{pid}/sync")
def sync(pid: int, user: dict = Depends(require_admin)):
    result = projects.sync_project(pid)
    audit(user["username"], "project.sync", projects.get_project(pid)["name"])
    return result


@router.get("/{pid}/session")
async def session_status(pid: int, user: dict = Depends(current_user)):
    """工程常驻会话状态（ADR-0046）。"""
    projects.get_project(pid)
    from .. import atr
    sid = f"atr-proj-{pid}"
    return {"session_id": sid, "exists": atr.session_exists(sid)}


@router.post("/{pid}/session/open")
async def session_open(pid: int, user: dict = Depends(require_admin)):
    """打开工程常驻会话：幂等 ensure（tmux 后端）+ 首次注入工程上下文（ADR-0046）。"""
    p = projects.get_project(pid)
    from .. import atr, registry
    sid = f"atr-proj-{pid}"
    try:
        created = atr.ensure_session(sid, cwd=atr.container_repo_path(pid),
                                     purpose=f"工程 {p['name']} 常驻会话")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"ATR 不可达或拒绝：{e}") from e
    context_written = False
    if created:
        skills = [c["name"] for c in registry.injectable_components()]
        context_written = atr.write_context_file(p, skills) is not None
        try:
            atr.send_text(sid, "cat ATR_CONTEXT.md 2>/dev/null || "
                               "echo '（无 ATR_CONTEXT.md：工作区克隆缺失）'")
        except Exception:  # noqa: BLE001 注入失败不影响会话使用
            pass
        audit(user["username"], "project.session_create", p["name"], f"session={sid}")
    return {"session_id": sid, "created": created, "context_written": context_written,
            "chat_url": atr.chat_url(sid)}
