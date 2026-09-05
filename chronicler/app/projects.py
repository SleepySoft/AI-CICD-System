"""工程（FR-MGR-020）：核心是一个 git 链接；clone/fetch 到宿主目录，供 harness 真实路径访问"""
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
from fastapi import HTTPException

from .config import Cfg
from .db import execute, loads, q, q1

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SHADOW_MAIN_BRANCH = "main"


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
        p["last_synced_at"] = p.get("last_synced_at") or None
        p["last_sync_error"] = p.get("last_sync_error") or ""
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
    """clone 或 fetch；本地路径/文件协议同样支持（git_url 可为 /path 或 file://）
    成功记录 last_synced_at 并清空 last_sync_error；失败记录错误后抛给 API（工程视图展示同步问题）"""
    p = get_project(pid)
    dest = repo_dir(pid)
    try:
        if dest.is_dir():
            if not _is_own_repo(dest):
                # 损坏克隆：禁止在其中执行任何 git 操作（会向上逃逸到宿主仓库）。
                # 程序不自行删除（清理是显式人工动作），引导用户走「重置克隆」。
                _mark_sync_error(pid, "工作区克隆已损坏（不是独立 git 仓库），请用「重置克隆」重建")
                raise HTTPException(status_code=409,
                                    detail="工作区克隆已损坏（不是独立 git 仓库），已阻止同步；"
                                           "请在工程页用「重置克隆」重建")
            r = _git(["-C", str(dest), "fetch", "--all", "--prune"], timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"git fetch 失败：{r.stderr.strip()[:500]}")
            branch = p.get("default_branch") or ""
            if branch:
                switched = _git(["-C", str(dest), "checkout", branch])
                if switched.returncode != 0:
                    raise RuntimeError(f"git checkout {branch} 失败：{switched.stderr.strip()[:500]}")
                reset = _git(["-C", str(dest), "reset", "--hard", f"origin/{branch}"])
                if reset.returncode != 0:
                    raise RuntimeError(f"git reset origin/{branch} 失败：{reset.stderr.strip()[:500]}")
            else:
                upstream = _git(["-C", str(dest), "rev-parse", "--abbrev-ref",
                                 "--symbolic-full-name", "@{upstream}"])
                if upstream.returncode == 0 and upstream.stdout.strip():
                    reset = _git(["-C", str(dest), "reset", "--hard", upstream.stdout.strip()])
                    if reset.returncode != 0:
                        raise RuntimeError(f"git reset {upstream.stdout.strip()} 失败："
                                           f"{reset.stderr.strip()[:500]}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            clone_args = (["clone", "-b", p["default_branch"], p["git_url"], str(dest)]
                          if p.get("default_branch") else ["clone", p["git_url"], str(dest)])
            r = _git(clone_args, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"git 同步失败：{r.stderr.strip()[:500]}")
        execute("UPDATE projects SET last_synced_at=strftime('%s','now'), last_sync_error='' WHERE id=?", (pid,))
        return {"ok": True, "last_commit": _last_commit(pid)}
    except subprocess.TimeoutExpired:
        _mark_sync_error(pid, "git 同步超时")
        raise HTTPException(status_code=504, detail="git 同步超时")
    except Exception as e:
        msg = getattr(e, "detail", None) or str(e)
        _mark_sync_error(pid, str(msg)[:500])
        raise


def _mark_sync_error(pid: int, msg: str) -> None:
    execute("UPDATE projects SET last_sync_error=? WHERE id=?", (msg, pid))


def _git(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """统一 git 调用：显式 UTF-8 解码（Windows 默认 GBK 遇 UTF-8 提交信息会炸）；
    剥离 http 代理（本系统 git 操作全是本机 Gitea / GitHub SSH，Clash 类代理会拦截假死）"""
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    # git 全局配置可能带 socks/http 代理（Clash），本系统 git 操作（本机 Gitea / GitHub SSH）都应直连
    return subprocess.run(["git", "-c", "http.proxy=", "-c", "https.proxy=", *args],
                          capture_output=True, env=env,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _is_own_repo(dest: Path) -> bool:
    """dest 必须是独立的 git 仓库（其 toplevel 就是自身）。
    损坏克隆（.git 残缺/丢失）时 git 会向上逃逸到宿主仓库——2026-09-05 实测：
    残缺的 data/workspace/repos/<id> 导致 reset --hard 打在主源码库上，丢掉未推送提交。"""
    r = _git(["-C", str(dest), "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        return False
    try:
        return os.path.normcase(str(Path(r.stdout.strip()).resolve())) == \
            os.path.normcase(str(dest.resolve()))
    except OSError:
        return False


def _last_commit(pid: int) -> str | None:
    """最近提交：hash + 提交时间 + 主题（%x1f 作分隔符，主题可能含任意字符）"""
    r = _git(["-C", str(repo_dir(pid)), "log", "-1",
              "--format=%h%x1f%ad%x1f%s", "--date=format:%Y-%m-%d %H:%M"])
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        return None
    parts = (out.split("\x1f", 2) + ["", ""])[:3]
    return {"hash": parts[0], "date": parts[1], "subject": parts[2]}


def reset_clone(pid: int) -> dict:
    """删除工作空间克隆并重新拉取（克隆损坏/远端 force push/工程换址场景）"""
    import shutil
    get_project(pid)
    shutil.rmtree(repo_dir(pid), ignore_errors=True)
    return sync_project(pid)


def repo_dirty(pid: int) -> bool:
    """工作区是否有未提交改动（Run 档案 §2.1.1 A 段 repo_status）"""
    r = _git(["-C", str(repo_dir(pid)), "status", "--porcelain"])
    return bool(r.stdout.strip()) if r.returncode == 0 else False


def shadow_dir(pid: int) -> Path:
    """项目影子库目录（FR-MGR-013/ADR-0028）：data/public/shadow/<工程名>-shadow（交换区，容器可读）"""
    p = get_project(pid)
    return Cfg.PUBLIC / "shadow" / f"{p['name']}-shadow"


def ensure_shadow_repo(pid: int) -> Path:
    """建立或获取 shadow 库：指定 shadow_repo 则 clone；未指定则尝试 Gitea 自动建仓
    <工程名>-shadow（幂等）；Gitea 不可达时纯本地仓。返回 git 仓路径。"""
    p = get_project(pid)
    dest = shadow_dir(pid)
    if (dest / ".git").is_dir():
        return dest
    url = (p.get("shadow_repo") or "").strip()
    if not url:
        url = _gitea_auto_shadow_repo(p) or ""  # 建仓成功会回写 project.shadow_repo
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url:
        r = _git(["clone", url, str(dest)], timeout=300)
        if r.returncode != 0:
            # clone 失败（如空仓 404）则本地初始化，推送时建仓
            dest.mkdir(parents=True, exist_ok=True)
            _git(["-C", str(dest), "init"])
            _git(["-C", str(dest), "commit", "--allow-empty", "-m", "init shadow repo"])
    else:
        dest.mkdir(parents=True, exist_ok=True)
        _git(["-C", str(dest), "init"])
        _git(["-C", str(dest), "commit", "--allow-empty", "-m", "init shadow repo"])
    return dest


def prepare_shadow_direct(pid: int) -> Path:
    """准备 direct 发布工作树：保持干净，并统一落在 main，不创建任务分支。"""
    dest = ensure_shadow_repo(pid)
    dirty = _git(["-C", str(dest), "status", "--porcelain"])
    if dirty.returncode != 0:
        raise RuntimeError(f"读取 shadow 工作树失败：{dirty.stderr.strip()[:300]}")
    if dirty.stdout.strip():
        raise RuntimeError("shadow 工作树存在未提交修改，拒绝混入新的 Run")

    current = _git(["-C", str(dest), "branch", "--show-current"])
    if current.stdout.strip() == SHADOW_MAIN_BRANCH:
        return dest
    exists = _git(["-C", str(dest), "show-ref", "--verify", "--quiet",
                   f"refs/heads/{SHADOW_MAIN_BRANCH}"])
    args = (["-C", str(dest), "checkout", SHADOW_MAIN_BRANCH] if exists.returncode == 0
            else ["-C", str(dest), "branch", "-M", SHADOW_MAIN_BRANCH])
    switched = _git(args)
    if switched.returncode != 0:
        raise RuntimeError(f"准备 shadow 主分支失败：{switched.stderr.strip()[:300]}")
    return dest


def shadow_head(pid: int) -> str:
    dest = ensure_shadow_repo(pid)
    r = _git(["-C", str(dest), "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else ""


def _gitea_auto_shadow_repo(project: dict) -> str | None:
    """Gitea 自动建仓 <工程名>-shadow（幂等，ADR-0028）；凭据环境注入。返回 clone URL 或 None"""
    user, pw = os.environ.get("GITEA_ADMIN_USER", ""), os.environ.get("GITEA_ADMIN_PASSWORD", "")
    if not (user and pw):
        return None
    try:
        gitea = next((t for t in load_tools_safe() if t["name"] == "gitea"), None)
        if not gitea:
            return None
        base = gitea.get("url", "http://git.localhost").rstrip("/")
        host = base.split("//")[1]
        api = f"http://127.0.0.1/api/v1" if host.endswith(".localhost") else f"{base}/api/v1"
        headers = {"Host": host} if host.endswith(".localhost") else {}
        repo_name = f"{project['name']}-shadow"
        with httpx.Client(timeout=10, trust_env=False) as client:
            auth = (user, pw)
            r = client.get(f"{api}/repos/{user}/{repo_name}", headers=headers, auth=auth)
            if r.status_code == 404:
                r = client.post(f"{api}/user/repos", headers=headers, auth=auth, json={
                    "name": repo_name,
                    "description": f"Chronicler shadow：{project['name']} 的分析报告与蒸馏文档（ADR-0028）",
                    "private": False, "auto_init": False})
                if r.status_code not in (200, 201, 409):
                    return None
            clone_url = f"{base}/{user}/{repo_name}.git"
            execute("UPDATE projects SET shadow_repo=? WHERE id=?", (clone_url, project["id"]))
            return clone_url
    except Exception:  # noqa: BLE001 - 建仓失败降级为本地仓
        return None


def load_tools_safe():
    from .tools import load_tools
    try:
        return load_tools()
    except Exception:
        return []


def push_shadow(pid: int, branch: str = SHADOW_MAIN_BRANCH) -> str | None:
    """shadow 库推送到工程指定的 shadow_repo（FR-MGR-013）；凭据运行期从环境注入，不落库"""
    p = get_project(pid)
    url = (p.get("shadow_repo") or "").strip()
    if not url:
        # 本地仓已存在但远端未登记：尝试 Gitea 自动建仓（幂等）并回写（ADR-0028）
        url = _gitea_auto_shadow_repo(p) or ""
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
    r = _git(["-C", str(dest), "push", push_url, f"HEAD:{branch}"], timeout=120)
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
