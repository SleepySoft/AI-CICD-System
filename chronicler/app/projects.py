"""工程（FR-MGR-020）：核心是一个 git 链接；clone/fetch 到宿主目录，供 harness 真实路径访问"""
import json
import os
import re
import subprocess
from pathlib import Path

from fastapi import HTTPException

from .config import Cfg
from .db import execute, loads, q, q1

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def repo_dir(project_id: int):
    return Cfg.repos_dir() / str(project_id)


def create_project(name: str, git_url: str, ci_url: str = "", description: str = "",
                   overrides: dict | None = None, default_branch: str = "", shadow_repo: str = "") -> dict:
    if not _NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="工程名仅允许小写字母/数字/-/_")
    if q1("SELECT id FROM projects WHERE name=?", (name,)):
        raise HTTPException(status_code=409, detail="工程名已存在")
    pid = execute(
        "INSERT INTO projects(name, git_url, default_branch, ci_url, shadow_repo, description, overrides, created_at)"
        " VALUES (?,?,?,?,?,?,?,strftime('%s','now'))",
        (name, git_url, default_branch, ci_url, shadow_repo, description, json.dumps(overrides or {}, ensure_ascii=False)))
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
    allowed = {k: v for k, v in fields.items() if k in ("git_url", "ci_url", "description", "default_branch", "shadow_repo")}
    if allowed or merged != p["overrides"]:
        sets = []
        args = []
        for k, v in allowed.items():
            sets.append(f"{k}=?")
            args.append(v)
        sets.append("overrides=?")
        args.append(json.dumps(merged, ensure_ascii=False))
        args.append(pid)
        execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", tuple(args))
    return get_project(pid)


def sync_project(pid: int) -> dict:
    """clone 或 fetch；本地路径/文件协议同样支持（git_url 可为 /path 或 file://）"""
    p = get_project(pid)
    dest = repo_dir(pid)
    try:
        if dest.is_dir():
            r = _git(["-C", str(dest), "fetch", "--all", "--prune"], timeout=300)
            branch = p.get("default_branch") or ""
            if branch:
                _git(["-C", str(dest), "checkout", branch])
                _git(["-C", str(dest), "reset", "--hard", f"origin/{branch}"])
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            clone_args = ["clone", p["git_url"], str(dest)]
            if p.get("default_branch"):
                clone_args = ["clone", "-b", p["default_branch"], p["git_url"], str(dest)]
            r = _git(clone_args, timeout=600)
        if r.returncode != 0:
            raise HTTPException(status_code=502, detail=f"git 同步失败：{r.stderr.strip()[:500]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="git 同步超时")
    return {"ok": True, "last_commit": _last_commit(pid)}


def _git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """统一 git 调用：显式 UTF-8 解码（Windows 默认 GBK 遇 UTF-8 提交信息会炸）；
    剥离 http 代理（本系统 git 操作全是本机 Gitea / GitHub SSH，Clash 类代理会拦截假死）"""
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    # git 全局配置可能带 socks/http 代理（Clash），本系统 git 操作（本机 Gitea / GitHub SSH）都应直连
    return subprocess.run(["git", "-c", "http.proxy=", "-c", "https.proxy=", *args],
                          capture_output=True, env=env,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _last_commit(pid: int) -> str | None:
    r = _git(["-C", str(repo_dir(pid)), "log", "-1", "--format=%h %s"])
    return r.stdout.strip() if r.returncode == 0 else None


def repo_dirty(pid: int) -> bool:
    """工作区是否有未提交改动（Run 档案 §2.1.1 A 段 repo_status）"""
    r = _git(["-C", str(repo_dir(pid)), "status", "--porcelain"])
    return bool(r.stdout.strip()) if r.returncode == 0 else False


def shadow_dir(pid: int) -> Path:
    """项目影子库目录（FR-MGR-013）：data/private/chronicler/shadow/<pid>"""
    return Cfg.DATA / "shadow" / str(pid)


def ensure_shadow_repo(pid: int) -> Path:
    """建立或同步 shadow 库：工程指定了 shadow_repo（URL/路径）则 clone；否则本地 init
    返回 shadow 库路径（git 仓库）"""
    p = get_project(pid)
    dest = shadow_dir(pid)
    if dest.is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if p.get("shadow_repo"):
        r = _git(["clone", p["shadow_repo"], str(dest)], timeout=300)
        if r.returncode != 0:
            raise HTTPException(status_code=502, detail=f"shadow 库 clone 失败：{r.stderr.strip()[:300]}")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        _git(["-C", str(dest), "init"])
        _git(["-C", str(dest), "commit", "--allow-empty", "-m", "init shadow repo"])
    return dest


def push_shadow(pid: int) -> str | None:
    """shadow 库推送到工程指定的 shadow_repo（FR-MGR-013）；凭据运行期从环境注入，不落库"""
    p = get_project(pid)
    url = (p.get("shadow_repo") or "").strip()
    if not url:
        return None
    dest = shadow_dir(pid)
    push_url = url
    if url.startswith("http"):
        user, pw = os.environ.get("GITEA_ADMIN_USER", ""), os.environ.get("GITEA_ADMIN_PASSWORD", "")
        if user and pw:
            from urllib.parse import urlparse, urlunparse
            u = urlparse(url)
            push_url = urlunparse(u._replace(netloc=f"{user}:{pw}@{u.netloc}"))
    r = _git(["-C", str(dest), "push", push_url, "HEAD:main"], timeout=120)
    if r.returncode != 0:
        raise HTTPException(status_code=502, detail=f"shadow 推送失败：{r.stderr.strip()[:300]}")
    return url


def head_commit(pid: int) -> str:
    r = _git(["-C", str(repo_dir(pid)), "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else ""


def recent_log(pid: int, n: int = 30) -> str:
    r = _git(["-C", str(repo_dir(pid)), "log", f"-{n}", "--format=%h %ad %an %s",
              "--date=short"])
    return r.stdout.strip()
