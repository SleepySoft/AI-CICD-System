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
    p = projects.create_project(body.name, body.git_url, body.ci_url, body.description,
                                body.overrides, body.default_branch, body.shadow_repo)
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


@router.delete("/{pid}")
async def delete(pid: int, user: dict = Depends(require_admin)):
    import shutil
    p = projects.get_project(pid)
    # 先清关联 Run（task_runs 有外键），再删工程；报告保留在 public/reports 供追溯
    projects.execute("DELETE FROM task_runs WHERE project_id=?", (pid,))
    projects.execute("DELETE FROM projects WHERE id=?", (pid,))
    shutil.rmtree(projects.repo_dir(pid), ignore_errors=True)  # 清理工作空间克隆
    audit(user["username"], "project.delete", p["name"])
    return {"ok": True}


@router.post("/{pid}/sync")
async def sync(pid: int, user: dict = Depends(require_admin)):
    result = projects.sync_project(pid)
    audit(user["username"], "project.sync", projects.get_project(pid)["name"])
    return result
