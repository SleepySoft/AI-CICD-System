"""任务定义路由：CRUD + 触发 + 启停（FR-MGR-004 前置形态）"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import tasks
from ..auth import current_user, require_admin
from ..db import audit

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    project_id: int
    name: str
    task_type: str
    cwd: str = ""
    schedule_cron: str = ""
    enabled: bool = True


class TaskPatch(BaseModel):
    name: str | None = None
    cwd: str | None = None
    schedule_cron: str | None = None
    webhook: bool | None = None
    enabled: bool | None = None
    prompt_override: str | None = None


@router.get("")
async def list_(project_id: int | None = None, user: dict = Depends(current_user)):
    return tasks.list_tasks(project_id)


@router.post("")
async def create(body: TaskBody, user: dict = Depends(require_admin)):
    t = tasks.create_task(body.project_id, body.name, body.task_type,
                          body.schedule_cron, body.enabled, body.cwd)
    audit(user["username"], "task.create", t["name"])
    return t


@router.get("/{tid}")
async def detail(tid: int, user: dict = Depends(current_user)):
    return tasks.get_task(tid)


@router.patch("/{tid}")
async def update(tid: int, body: TaskPatch, user: dict = Depends(require_admin)):
    t = tasks.update_task(tid, body.model_dump(exclude_none=True))
    audit(user["username"], "task.update", t["name"])
    return t


@router.delete("/{tid}")
async def delete(tid: int, user: dict = Depends(require_admin)):
    r = tasks.delete_task(tid)
    audit(user["username"], "task.delete", r["name"])
    return r


@router.post("/{tid}/trigger")
async def trigger(tid: int, user: dict = Depends(require_admin)):
    run = tasks.trigger_task(tid, user["username"])
    audit(user["username"], "task.trigger", f"task#{tid}->run#{run['id']}")
    return run
