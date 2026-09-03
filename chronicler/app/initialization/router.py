"""Web 初始化 API；所有写操作均受一次性引导会话或 admin 保护。"""
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import catalog, config_store, orchestrator, planner, preflight as preflight_checks, security, store
from .lifecycle import public_status

router = APIRouter(prefix="/api/setup", tags=["setup"])
page_router = APIRouter(tags=["setup-page"])
STATIC = Path(__file__).parent / "static"


@page_router.get("/setup", include_in_schema=False)
async def setup_page():
    return FileResponse(STATIC / "index.html")


class UnlockBody(BaseModel):
    code: str


class DraftBody(BaseModel):
    stage: str = "preflight"
    profile: str = "recommended"
    selections: list[str] = Field(default_factory=list)
    values: dict[str, str | int | bool] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


@router.get("/status")
async def status():
    result = public_status()
    draft = store.get_draft()
    result["progress"] = {"stage": draft["stage"], "revision": draft["revision"]}
    return result


@router.post("/unlock")
async def unlock(body: UnlockBody, response: Response):
    token = security.exchange(body.code)
    response.set_cookie(security.COOKIE, token, max_age=security.MAX_AGE,
                        httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/catalog")
async def get_catalog():
    return catalog.public_catalog()


@router.get("/preflight")
async def preflight(user=Depends(security.require_setup_session)):
    return preflight_checks.run(store.get_draft())


@router.get("/draft")
async def draft(user=Depends(security.require_setup_session)):
    result = store.get_draft()
    result["secrets"] = config_store.configured_presence(catalog.load())
    return result


@router.put("/draft")
async def save_draft(body: DraftBody, user=Depends(security.require_setup_session)):
    if store.one("SELECT id FROM setup_runs WHERE status='running'"):
        raise HTTPException(status_code=409, detail="部署正在执行，不能修改已确认配置；请先取消运行")
    try:
        entries = catalog.load()
        allowed_values = config_store.GLOBAL_VALUE_KEYS | {
            field["key"] for entry in entries.values()
            for field in entry.get("component", {}).get("fields", []) if field.get("kind") != "secret"
        }
        unknown_values = set(body.values) - allowed_values
        if unknown_values:
            raise ValueError("未知或必须作为秘密提交的配置键：" + "、".join(sorted(unknown_values)))
        allowed = {"INIT_ADMIN_USERNAME", "INIT_ADMIN_PASSWORD"} | config_store.GLOBAL_SECRET_KEYS | {
            field["key"] for entry in entries.values()
            for field in entry.get("component", {}).get("fields", []) if field.get("kind") == "secret"
        }
        unknown = set(body.secrets) - allowed
        if unknown:
            raise ValueError("未知秘密配置键：" + "、".join(sorted(unknown)))
        config_store.set_secrets(body.secrets)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return store.save_draft(body.stage, body.profile, body.selections, body.values,
                            config_store.configured_presence(entries))


@router.post("/plan")
async def make_plan(user=Depends(security.require_setup_session)):
    draft = store.get_draft()
    try:
        entries = catalog.load()
        selected, _ = planner._selected(draft["profile"], draft["selections"], entries)
        missing = []
        secret_presence = config_store.configured_presence(entries)
        for name in selected:
            for field in entries[name]["component"].get("fields", []):
                if field.get("required") and field.get("kind") == "secret" and not secret_presence.get(field["key"]):
                    missing.append(field.get("label") or field["key"])
        if not secret_presence.get("INIT_ADMIN_PASSWORD"):
            missing.append("本地恢复管理员密码")
        if not secret_presence.get("CHRONICLER_SECRET"):
            missing.append("Chronicler 会话密钥")
        if missing:
            raise ValueError("缺少必填秘密配置：" + "、".join(missing))
        readiness = preflight_checks.run(draft, require_docker=bool(selected))
        blocked = [item for item in readiness["checks"] if item["status"] == "block"]
        if blocked:
            raise ValueError("；".join(item["message"] for item in blocked))
        result = planner.build(draft["profile"], draft["selections"], draft["values"], draft["revision"],
                       secret_presence)
        return orchestrator.save_plan(result)
    except (planner.PlanError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: int, user=Depends(security.require_setup_session)):
    result = orchestrator.get_plan(plan_id)
    if not result:
        raise HTTPException(status_code=404, detail="计划不存在")
    return result


@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: int, user=Depends(security.require_setup_session)):
    try:
        check = preflight_checks.run(store.get_draft(), require_docker=True)
        blocked = [item for item in check["checks"] if item["status"] == "block"]
        if blocked:
            raise ValueError("执行前环境复核失败：" + "；".join(item["message"] for item in blocked))
        return {"run_id": orchestrator.create_run(plan_id)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/runs/{run_id}")
async def get_run(run_id: int, user=Depends(security.require_setup_session)):
    result = orchestrator.run_status(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="运行不存在")
    return result


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int, user=Depends(security.require_setup_session)):
    orchestrator.cancel(run_id)
    return {"ok": True}


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: int, user=Depends(security.require_setup_session)):
    try:
        return {"run_id": orchestrator.retry(run_id)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int, after: int = 0, user=Depends(security.require_setup_session)):
    if not orchestrator.run_status(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")

    async def stream():
        cursor = after
        while True:
            events = store.all_("SELECT * FROM setup_events WHERE run_id=? AND id>? ORDER BY id", (run_id, cursor))
            for event in events:
                cursor = event["id"]
                yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            run = store.one("SELECT status FROM setup_runs WHERE id=?", (run_id,))
            if run and run["status"] != "running" and not events:
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/history")
async def history(user=Depends(security.require_setup_session)):
    return orchestrator.history()


@router.get("/diagnostics")
async def diagnostics(user=Depends(security.require_setup_session)):
    return {"status": public_status(), "catalog": catalog.public_catalog(),
            "runs": orchestrator.history(),
            "note": "诊断响应不包含配置值、秘密、子进程环境或原始命令行"}