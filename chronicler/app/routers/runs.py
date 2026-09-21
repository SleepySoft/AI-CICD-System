"""任务/Run 路由：触发仅 admin；查询与日志全员可读（FR-MGR-005）"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import runner
from ..auth import current_user, require_admin
from ..config import Cfg
from ..db import audit
from ..runtime import PROFILE

router = APIRouter(prefix="/api/runs", tags=["runs"])


class TriggerBody(BaseModel):
    project_id: int
    task_type: str = "operational_reporter"
    extra_prompt: str = ""


@router.get("")
async def list_runs(project_id: int | None = None, user: dict = Depends(current_user)):
    return runner.list_runs(project_id)


@router.post("/trigger")
async def trigger(body: TriggerBody, user: dict = Depends(require_admin)):
    try:
        run = runner.trigger(body.project_id, body.task_type, user["username"], body.extra_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    audit(user["username"], "run.trigger", f"run#{run['id']}", body.task_type)
    return run


@router.get("/change-preview")
async def change_preview(project_id: int, task_type: str,
                         user: dict = Depends(require_admin)):
    from .. import change_detection, projects, registry
    registry.get_task_type(task_type)
    projects.sync_project(project_id)
    return change_detection.capture(project_id, task_type)


@router.get("/{run_id}")
async def detail(run_id: int, user: dict = Depends(current_user)):
    return runner.get_run(run_id)


@router.get("/{run_id}/log", response_class=PlainTextResponse)
async def log(run_id: int, user: dict = Depends(current_user)):
    run = runner.get_run(run_id)
    path = Path(run["log_path"] or "")
    if not path.is_file():
        return "（暂无日志）"
    # 旧日志可能是 GBK 原始字节：先解码归一，保证页面 UTF-8 显示不乱码
    return runner._decode_bytes(path.read_bytes())[-200_000:]


@router.get("/{run_id}/report", response_class=PlainTextResponse)
async def report(run_id: int, user: dict = Depends(current_user)):
    run = runner.get_run(run_id)
    path = Path(run["report_path"] or "")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无报告")
    return runner._decode_bytes(path.read_bytes())


@router.get("/{run_id}/prompt", response_class=PlainTextResponse)
async def prompt(run_id: int, user: dict = Depends(current_user)):
    """本次执行实际使用的渲染后 prompt 全文（A 段，FR-MGR-005）；
    优先 DB 记录，老数据回落 runs/<id>/prompt.md 文件。"""
    run = runner.get_run(run_id)
    if not PROFILE.persist_rendered_prompt:
        snapshot = run.get("input_snapshot") or {}
        return ("sealed 模式不披露渲染后 Prompt\n\n"
            f"name: {snapshot.get('prompt_name', 'unknown')}\n"
            f"version: {snapshot.get('prompt_version') or run.get('prompt_version', 'unknown')}\n"
            f"hash: {snapshot.get('prompt_hash', 'unknown')}\n")
    if run.get("prompt_text"):
        return run["prompt_text"]
    path = Cfg.runs_dir() / str(run_id) / "prompt.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="尚无 prompt 记录")
    return runner._decode_bytes(path.read_bytes())
