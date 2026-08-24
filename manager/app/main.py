"""Manager 入口"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import agent, auth, tools

app = FastAPI(title="AISystem Manager", docs_url=None, redoc_url=None)

app.include_router(auth.router)
app.include_router(tools.router)
app.include_router(agent.router)

STATIC = Path(__file__).parent / "static"


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "manager"}


@app.exception_handler(404)
async def not_found(request, exc):
    # SPA 前端路由回退（仅对非 API 路径）
    if not request.url.path.startswith("/api/"):
        return FileResponse(STATIC / "index.html")
    return JSONResponse({"detail": "not found"}, status_code=404)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
