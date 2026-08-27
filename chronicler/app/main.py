"""Chronicler supervisor 入口（ADR-0020：宿主侧进程）"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import auth, config, projects, runs, tools, users

app = FastAPI(title="Chronicler", docs_url=None, redoc_url=None)

db.init()

for r in (auth.router, users.router, projects.router, runs.router, config.router, tools.router):
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
