"""隐藏的管理员资源清理入口；页面和 API 均校验权限。"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import maintenance
from ..auth import require_admin
from ..config import Cfg

router = APIRouter(tags=["maintenance"])


class ProjectCleanup(BaseModel):
    targets: list[str]
    token: str
    confirmation: str


class OrphanCleanup(BaseModel):
    token: str
    confirmation: str


@router.get("/maintenance/cleanup", include_in_schema=False)
def page(user: dict = Depends(require_admin)):
    return FileResponse(Cfg.STATIC_DIR / "_maintenance.html")


@router.get("/api/maintenance/cleanup/preview")
def preview(user: dict = Depends(require_admin)):
    return maintenance.preview()


@router.post("/api/maintenance/cleanup/projects/{pid}")
def clean_project(pid: int, body: ProjectCleanup, user: dict = Depends(require_admin)):
    return maintenance.clean_project(pid, body.targets, body.token, body.confirmation,
                                     user["username"])


@router.post("/api/maintenance/cleanup/orphans/{name}")
def clean_orphan(name: str, body: OrphanCleanup, user: dict = Depends(require_admin)):
    return maintenance.clean_orphan(name, body.token, body.confirmation, user["username"])
