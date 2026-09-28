"""显式清理可重建的工程资源；预览与执行使用同一事实清单。"""
import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from . import projects
from .auditing import record
from .config import Cfg
from .db import execute, q, q1


def _safe_child(root: Path, name: str) -> Path:
    """拒绝符号链接、junction、穿越与意外路径；删除前再次调用。"""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise HTTPException(409, "资源目录名异常，已阻止清理")
    base = root.resolve()
    target = root / name
    if target.resolve() != base / name or target.is_symlink():
        raise HTTPException(409, "资源路径指向工作区外，已阻止清理")
    return target


def _remove(root: Path, name: str) -> bool:
    target = _safe_child(root, name)
    if not os.path.lexists(target):
        return False
    if not target.is_dir():
        raise HTTPException(409, "资源路径不是目录，已阻止清理")
    try:
        shutil.rmtree(target, onerror=projects._retry_readonly_removal)
        if os.path.lexists(target):
            raise OSError("清理后目录仍存在")
    except OSError as exc:
        raise HTTPException(409, "目录删除失败；请关闭占用该目录的程序后重试") from exc
    return True


def _remote_display(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https"}:
        return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
    return "已配置远端（地址未展示）"


def _local_head(path: Path) -> str:
    if not (path / ".git").exists() or not projects._is_own_repo(path):
        return ""
    result = projects._git(["-C", str(path), "rev-parse", "--verify", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def _tree_revision(path: Path) -> str:
    """目录元数据指纹；预览后新增/修改文件会使清理确认失效。"""
    if not path.is_dir():
        return "missing"
    digest = hashlib.sha256()
    for current, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            entry = Path(current) / name
            stat_result = entry.lstat()
            relative = entry.relative_to(path).as_posix()
            digest.update(f"{relative}\0{stat_result.st_mode}\0{stat_result.st_size}\0"
                          f"{stat_result.st_mtime_ns}\n".encode("utf-8", errors="surrogateescape"))
    return digest.hexdigest()


def _path_safe(root: Path, name: str) -> bool:
    try:
        _safe_child(root, name)
        return True
    except (HTTPException, OSError):
        return False


def _project_item(project: dict) -> dict:
    pid = project["id"]
    shadow_root, shadow_name = Cfg.PUBLIC / "shadow", f"{project['name']}-shadow"
    clone_root, clone_name = Cfg.repos_dir(), str(pid)
    shadow, clone = shadow_root / shadow_name, clone_root / clone_name
    shadow_safe = _path_safe(shadow_root, shadow_name)
    clone_safe = _path_safe(clone_root, clone_name)
    active = q("SELECT id, status FROM task_runs WHERE project_id=? AND status IN ('queued','running')",
               (pid,))
    recent = q1("SELECT id, publication FROM task_runs WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,))
    from .db import loads
    publication = loads(recent["publication"]) if recent else {}
    return {"id": pid, "name": project["name"],
            "local_shadow": shadow.is_dir(), "local_head": _local_head(shadow) if shadow_safe and shadow.is_dir() else "",
            "local_revision": _tree_revision(shadow) if shadow_safe else "unsafe",
            "remote_shadow": _remote_display(project.get("shadow_repo") or ""),
            "source_clone": clone.is_dir(), "active_runs": active,
            "clone_revision": _tree_revision(clone) if clone_safe else "unsafe",
            "unsafe_targets": [name for name, safe in (("local_shadow", shadow_safe),
                                                           ("source_clone", clone_safe)) if not safe],
            "last_run": recent["id"] if recent else None,
            "last_push_status": publication.get("push_status") or "unknown"}


def preview() -> dict:
    known = q("SELECT id, name, shadow_repo FROM projects ORDER BY id")
    project_items = [_project_item(p) for p in known]
    ids = {str(p["id"]) for p in known}
    root = Cfg.repos_dir()
    orphans = []
    sequence = q1("SELECT seq FROM sqlite_sequence WHERE name='projects'")
    highest_allocated = sequence["seq"] if sequence else 0
    if root.is_dir():
        for child in root.iterdir():
            if child.name not in ids and child.is_dir():
                safe = (_path_safe(root, child.name) and child.name.isdecimal() and
                        str(int(child.name)) == child.name and int(child.name) <= highest_allocated)
                orphans.append({"name": child.name, "safe": safe,
                                "independent_git": projects._is_own_repo(child) if safe else False,
                                "revision": _tree_revision(child) if safe else "unsafe"})
    facts = {"projects": project_items, "orphan_clones": orphans}
    # token 同时约束资源名、远端配置、当前 HEAD 和活动任务状态。
    remote_revisions = [(p["id"], p.get("shadow_repo") or "") for p in known]
    digest = hashlib.sha256(json.dumps([facts, remote_revisions], ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()
    return {**facts, "token": digest}


def clean_project(pid: int, targets: list[str], token: str, confirmation: str, actor: str) -> dict:
    allowed = {"local_shadow", "remote_shadow", "source_clone"}
    selected = set(targets)
    if not selected or len(selected) != len(targets) or not selected <= allowed:
        raise HTTPException(422, "请选择有效且不重复的清理目标")
    if "remote_shadow" in selected and "local_shadow" not in selected:
        raise HTTPException(422, "删除远端 Shadow 时必须同时清理本地 Shadow")
    gate = projects.project_gate(pid)
    if not gate.acquire(blocking=False):
        raise HTTPException(409, "工程正在接收任务，无法清理")
    lock = projects.repo_lock(pid)
    if not lock.acquire(blocking=False):
        gate.release()
        raise HTTPException(409, "工程正在使用，无法清理")
    try:
        project = projects.get_project(pid)
        if confirmation != f"删除 {project['name']}":
            raise HTTPException(422, "确认文字不匹配")
        current = preview()
        if token != current["token"]:
            raise HTTPException(409, "资源清单已变化，请重新预览并确认")
        item = next(p for p in current["projects"] if p["id"] == pid)
        if item["active_runs"]:
            raise HTTPException(409, "工程仍有排队或运行中的任务，请等待完成")
        if "remote_shadow" in selected and not project.get("shadow_repo"):
            raise HTTPException(409, "此工程未配置 Shadow 远端")
        if "local_shadow" in selected:
            _safe_child(Cfg.PUBLIC / "shadow", f"{project['name']}-shadow")
        if "source_clone" in selected:
            _safe_child(Cfg.repos_dir(), str(pid))
        # 先删远端：远端失败时，保留本地未推送提交供人工恢复。
        done = []
        try:
            if "remote_shadow" in selected:
                from .component_exec import run_capability
                result = run_capability("repos.py", ["delete", f"{project['name']}-shadow"],
                                        env={"CHRONICLER_EXPECTED_REPO_URL": project["shadow_repo"]})
                if not result or not result.get("ok"):
                    raise HTTPException(502, "Shadow 远端删除失败或无受管组件；本地资源未删除")
                execute("UPDATE projects SET shadow_repo='' WHERE id=?", (pid,))
                done.append("remote_shadow")
            if "local_shadow" in selected:
                _remove(Cfg.PUBLIC / "shadow", f"{project['name']}-shadow")
                done.append("local_shadow")
            if "source_clone" in selected:
                _remove(Cfg.repos_dir(), str(pid))
                done.append("source_clone")
        except Exception as exc:
            record("maintenance.cleanup", f"project#{pid}", actor=actor, result="failed",
                   selected=sorted(selected), completed=done, error_class=type(exc).__name__)
            raise
        record("maintenance.cleanup", f"project#{pid}", actor=actor,
               selected=sorted(selected), completed=done)
        return {"ok": True, "completed": done}
    finally:
        lock.release()
        gate.release()


def clean_orphan(name: str, token: str, confirmation: str, actor: str) -> dict:
    if confirmation != f"删除残留 {name}":
        raise HTTPException(422, "确认文字不匹配")
    current = preview()
    if token != current["token"]:
        raise HTTPException(409, "资源清单已变化，请重新预览并确认")
    if name not in {item["name"] for item in current["orphan_clones"] if item["safe"]}:
        raise HTTPException(409, "目标已不属于残留克隆")
    # 残留编号也取得工程锁，防止新建工程复用该编号时与运行任务相撞。
    lock = projects.project_gate(int(name)) if name.isdecimal() else None
    if lock and not lock.acquire(blocking=False):
        raise HTTPException(409, "目录正在使用，无法清理")
    try:
        if q1("SELECT id FROM projects WHERE id=?", (name,)):
            raise HTTPException(409, "目录已成为工程克隆，请重新预览")
        _remove(Cfg.repos_dir(), name)
        record("maintenance.cleanup", f"orphan-clone/{name}", actor=actor, selected=["orphan_clone"])
        return {"ok": True, "completed": ["orphan_clone"]}
    finally:
        if lock:
            lock.release()
