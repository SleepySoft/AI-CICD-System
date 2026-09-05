"""Chronicler supervisor 应用工厂（normal/bootstrap/repair）。"""
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Cfg


def create_app(mode: str = "normal") -> FastAPI:
    app = FastAPI(title="Chronicler", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def mode_guard(request, call_next):
        if mode == "bootstrap":
            path = request.url.path
            allowed = (path == "/api/health" or path == "/setup" or
                       path.startswith("/api/setup/") or path.startswith("/setup-assets/"))
            if not allowed:
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "系统尚未初始化"}, status_code=503)
                return FileResponse(Path(__file__).parent / "initialization" / "static" / "index.html")
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    async def health():
        return {"ok": mode != "repair", "service": "chronicler", "version": "1.0.0", "mode": mode}

    from .initialization.router import page_router, router as setup_router
    setup_static = Path(__file__).parent / "initialization" / "static"
    app.include_router(page_router)
    app.include_router(setup_router)
    app.mount("/setup-assets", StaticFiles(directory=setup_static), name="setup-assets")

    if mode == "bootstrap":
        @app.on_event("startup")
        def _resume_setup():
            from .initialization.orchestrator import resume_active
            resume_active()
        return app

    if mode == "repair":
        @app.get("/", include_in_schema=False)
        async def repair_page():
            return JSONResponse({"detail": "已初始化实例缺少 .env；为安全起见未开放引导写权限",
                                 "remediation": "请在宿主恢复 .env 后重启 Chronicler"}, status_code=503)
        return app

    from . import db
    db.init()

    from .tasks import backfill_preset_tasks, start_scheduler
    backfill_preset_tasks()
    start_scheduler()

    from .routers import auth, config, oidc, projects, runs, tasks, tools, users, vault
    for item in (auth.router, oidc.router, users.router, projects.router, runs.router,
                 tasks.router, config.router, tools.router, vault.router):
        app.include_router(item)

    @app.on_event("startup")
    def _autostart_boot():
        from .tools import autostart_boot
        threading.Thread(target=autostart_boot, daemon=True).start()

    static = Cfg.STATIC_DIR

    @app.exception_handler(404)
    async def not_found(request, exc):
        if not request.url.path.startswith("/api/"):
            return FileResponse(static / "index.html")
        return JSONResponse({"detail": "not found"}, status_code=404)

    app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app
