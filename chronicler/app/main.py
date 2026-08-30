"""Chronicler supervisor 入口（ADR-0020：宿主侧进程）"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import auth, config, oidc, projects, runs, tasks, tools, users

app = FastAPI(title="Chronicler", docs_url=None, redoc_url=None)


@app.middleware("http")
async def no_cache_static(request, call_next):
    """静态资源禁用缓存（前端无构建步骤，文件名不带指纹，靠 no-store 防陈旧）"""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

db.init()

# 存量工程补齐预置任务（幂等）+ 任务调度器（cron 触发，FR-MGR-004 前置形态）
from .tasks import backfill_preset_tasks, start_scheduler
backfill_preset_tasks()
start_scheduler()


@app.on_event("startup")
def _autostart_boot():
    """启动钩子（后台线程，不阻塞服务就绪）：拉起标记自启的组件（FR-MGR-022）"""
    import threading
    from .tools import autostart_boot
    threading.Thread(target=autostart_boot, daemon=True).start()


for r in (auth.router, oidc.router, users.router, projects.router, runs.router,
          tasks.router, config.router, tools.router):
    app.include_router(r)

STATIC = Path(__file__).parent / "static"


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "chronicler", "version": "1.0.0"}


@app.exception_handler(404)
async def not_found(request, exc):
    if not request.url.path.startswith("/api/"):
        return FileResponse(STATIC / "index.html")
    return JSONResponse({"detail": "not found"}, status_code=404)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
