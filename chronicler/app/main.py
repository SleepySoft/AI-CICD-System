"""Chronicler supervisor 应用工厂（normal/bootstrap/repair）。"""
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import Cfg
from .auditing import scope, stage, record, context


def create_app(mode: str = "normal") -> FastAPI:
    from . import db
    db.init()
    from .compatibility import check as compatibility_check

    result = compatibility_check()
    import sys

    print(f"[COMPATIBILITY] components={len(result['components'])} "
          f"runtime-unverified={sum(item['deployed_revision'] is None for item in result['components'])} "
          f"shadow={len(result['workspaces'])} gaps={len(result['issues'])}", file=sys.stderr)
    if result["issues"]:
        for issue in result["issues"]:
            print(f"[COMPATIBILITY GAP] {issue['scope']}/{issue['name']}: {issue['message']}", file=sys.stderr)
            record("runtime.compatibility_gap", f"{issue['scope']}/{issue['name']}",
                   result="blocked", gap_code=issue["code"])
    with scope(actor="supervisor", source="runtime-startup", mode=mode,
               correlation_id=uuid.uuid4().hex):
        with stage("runtime.initialize"):
            return _create_app(mode)


def _create_app(mode: str) -> FastAPI:
    app = FastAPI(title="Chronicler", docs_url=None, redoc_url=None)
    startup_context = context()

    @app.middleware("http")
    async def operation_audit(request, call_next):
        from .auth import read_session
        from .db import q1
        username = read_session(request.cookies.get(Cfg.SESSION_COOKIE, ""))
        user = q1("SELECT username FROM users WHERE username=?", (username,)) if username else None
        with scope(actor=user["username"] if user else "anonymous", source="http",
                   correlation_id=uuid.uuid4().hex):
            mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
            try:
                response = await call_next(request)
            except Exception as exc:
                if mutation:
                    record("http.mutation", request.url.path, result="failed",
                           method=request.method, error_class=type(exc).__name__)
                raise
            if mutation:
                record("http.mutation", request.url.path,
                       result="success" if response.status_code < 400 else "failed",
                       method=request.method, status_code=response.status_code)
            return response

    @app.middleware("http")
    async def mode_guard(request, call_next):
        # 发行资源中的页面文件只能经管理员路由提供，静态文件挂载不可直出。
        if request.url.path == "/_maintenance.html":
            return JSONResponse({"detail": "not found"}, status_code=404)
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
        from chronicler import __version__

        return {"ok": mode != "repair", "service": "chronicler", "version": __version__, "mode": mode}

    from .initialization.router import page_router, router as setup_router
    setup_static = Path(__file__).parent / "initialization" / "static"
    app.include_router(page_router)
    app.include_router(setup_router)
    app.mount("/setup-assets", StaticFiles(directory=setup_static), name="setup-assets")

    if mode == "bootstrap":
        @app.on_event("startup")
        def _resume_setup():
            from .initialization.orchestrator import resume_active
            with scope(**startup_context):
                with stage("runtime.setup_resume"):
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

    from .vault.sync import EnvConflict
    try:  # ADR-0045：存量明文 .env 自动迁移——导入秘密库后糊化（锁定时跳过）
        from .initialization import catalog as _catalog
        from .vault import sync as _vault_sync
        with stage("runtime.secret_migration"):
            _vault_sync.migrate_env_to_masked(_catalog.load())
        # 糊化后 Chronicler 自身秘密（会话密钥/OIDC 密钥）从秘密库解析进进程
        with stage("runtime.session_secrets"):
            _vault_sync.apply_chronicler_secrets()
    except EnvConflict:
        raise  # 不允许旧 .env 值随自启部署覆盖秘密库事实源。
    except Exception:  # noqa: BLE001 锁定仍允许管理员进入解锁页
        record("runtime.initialize_degraded", result="failed", reason="secret-initialization-failed")
        import traceback
        traceback.print_exc()

    from .tasks import backfill_preset_tasks, start_scheduler
    with stage("runtime.task_backfill"):
        backfill_preset_tasks()
    with stage("runtime.scheduler"):
        start_scheduler()

    from .routers import auth, config, oidc, projects, runs, tasks, tools, users, vault, audit, maintenance
    for item in (auth.router, oidc.router, users.router, projects.router, runs.router,
                 tasks.router, config.router, tools.router, vault.router, audit.router,
                 maintenance.router):
        app.include_router(item)

    @app.on_event("startup")
    def _autostart_boot():
        from .tools import autostart_boot
        def boot():
            with scope(**{**startup_context, "source": "runtime-autostart"}):
                try:
                    with stage("runtime.components_autostart") as outcome:
                        outcome["result"] = "failed" if autostart_boot() == "error" else "success"
                finally:
                    db.close()
        threading.Thread(target=boot, daemon=True).start()

    static = Cfg.STATIC_DIR

    @app.get("/", include_in_schema=False)
    async def index_page(request: Request):
        """按设备分流：手机浏览器进移动工作台 /m，其余进桌面 SPA。"""
        ua = request.headers.get("user-agent", "").lower()
        if any(k in ua for k in ("mobile", "android", "iphone", "ipod")):
            return RedirectResponse("/m")
        return FileResponse(static / "index.html")

    @app.get("/m", include_in_schema=False)
    async def mobile_page():
        """移动工作台入口（手机布局 + 前后台切换稳定；静态页在 static/mobile.html）。"""
        return FileResponse(static / "mobile.html")

    @app.exception_handler(404)
    async def not_found(request, exc):
        if not request.url.path.startswith("/api/"):
            return FileResponse(static / "index.html")
        return JSONResponse({"detail": "not found"}, status_code=404)

    app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app
