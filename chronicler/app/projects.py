"""工程（FR-MGR-020）：核心是一个 git 链接；clone/fetch 到宿主目录，供 harness 真实路径访问"""
import json
import re
import subprocess

from fastapi import HTTPException

from .config import Cfg
from .db import execute, loads, q, q1

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def repo_dir(project_id: int):
    return Cfg.repos_dir() / str(project_id)


def create_project(name: str, git_url: str, ci_url: str = "", description: str = "",
                   overrides: dict | None = None) -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="工程名仅允许小写字母/数字/-/_")
    if q1("SELECT id FROM projects WHERE name=?", (name,)):
        raise HTTPException(status_code=409, detail="工程名已存在")
    pid = execute(
        "INSERT INTO projects(name, git_url, ci_url, description, overrides, created_at)"
        " VALUES (?,?,?,?,?,strftime('%s','now'))",
        (name, git_url, ci_url, description, json.dumps(overrides or {}, ensure_ascii=False)))
    return get_project(pid)


def get_project(pid: int) -> dict:
    p = q1("SELECT * FROM projects WHERE id=?", (pid,))
    if not p:
        raise HTTPException(status_code=404, detail="工程不存在")
    p["overrides"] = loads(p["overrides"])
    return p


def list_projects() -> list[dict]:
    rows = q("SELECT * FROM projects ORDER BY id")
    for p in rows:
        p["overrides"] = loads(p["overrides"])
        p["synced"] = repo_dir(p["id"]).is_dir()
        p["last_commit"] = _last_commit(p["id"]) if p["synced"] else None
    return rows


def update_project(pid: int, fields: dict) -> dict:
    p = get_project(pid)
    merged = {**p["overrides"], **(fields.pop("overrides", {}) or {})}
    allowed = {k: v for k, v in fields.items() if k in ("git_url", "ci_url", "description")}
    if allowed or merged != p["overrides"]:
        sets = ", ".join(f"{k}=?" for k in allowed)
        args = list(allowed.values())
        sets += ", overrides=?"
        args.append(json.dumps(merged, ensure_ascii=False))
        args.append(pid)
        execute(f"UPDATE projects SET {sets} WHERE id=?", tuple(args))
    return get_project(pid)


def sync_project(pid: int) -> dict:
    """clone 或 fetch；本地路径/文件协议同样支持（git_url 可为 /path 或 file://）"""
    p = get_project(pid)
    dest = repo_dir(pid)
    try:
        if dest.is_dir():
            r = _git(["-C", str(dest), "fetch", "--all", "--prune"], timeout=300)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = _git(["clone", p["git_url"], str(dest)], timeout=600)
        if r.returncode != 0:
            raise HTTPException(status_code=502, detail=f"git 同步失败：{r.stderr.strip()[:500]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="git 同步超时")
    return {"ok": True, "last_commit": _last_commit(pid)}


def _git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """统一 git 调用：显式 UTF-8 解码（Windows 默认 GBK 遇到 UTF-8 提交信息会炸）"""
    return subprocess.run(["git", *args], capture_output=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _last_commit(pid: int) -> str | None:
    r = _git(["-C", str(repo_dir(pid)), "log", "-1", "--format=%h %s"])
    return r.stdout.strip() if r.returncode == 0 else None


def repo_dirty(pid: int) -> bool:
    """工作区是否有未提交改动（Run 档案 §2.1.1 A 段 repo_status）"""
    r = _git(["-C", str(repo_dir(pid)), "status", "--porcelain"])
    return bool(r.stdout.strip()) if r.returncode == 0 else False


def head_commit(pid: int) -> str:
    r = _git(["-C", str(repo_dir(pid)), "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else ""


def recent_log(pid: int, n: int = 30) -> str:
    r = _git(["-C", str(repo_dir(pid)), "log", f"-{n}", "--format=%h %ad %an %s",
              "--date=short"])
    return r.stdout.strip()
