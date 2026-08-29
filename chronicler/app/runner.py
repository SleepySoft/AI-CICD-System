"""任务执行器（M2 harness 执行器）：subprocess 一次性会话拉起 agent CLI（ADR-0021）

v1 边界：仅 once 会话（持久/resume 为 ADR-0021 标注的 TBD，后续版本）；
手动触发；日志落文件，前端轮询（SSE 留待后续）。
Run 档案契约见 docs/what/manager.md §2.1.1（A 输入快照 / B 执行过程 / C 产物清单）。
"""
import json
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

import httpx
from fastapi import HTTPException

from . import projects, registry
from .config import Cfg
from .db import audit, dumps, execute, q, q1

_harness_locks: dict[str, threading.Lock] = {}


def _harness_lock(name: str) -> threading.Lock:
    """同 harness 串行锁：kimi 等 CLI 有全局日志文件锁，并发实例会互抢（实测 WinError 32）"""
    if name not in _harness_locks:
        _harness_locks[name] = threading.Lock()
    return _harness_locks[name]


def _q(path: str) -> str:
    """跨平台路径引号：Windows cmd 用双引号，POSIX 用 shlex（ADR-0020 多平台）"""
    return f'"{path}"' if os.name == "nt" else shlex.quote(path)


def _render_prompt(template: str, project: dict, extra: dict) -> str:
    # ADR-0024/0025：注入 L0 摘要（名称+一句话+SKILL 路径），agent 按需自读 SKILL.md
    comps = registry.injectable_components()
    if comps:
        lines = [f"- {c['name']}: {c['desc']}（能力详情见 SKILL 文件：{c['skill']}，需要时再读）"
                 for c in comps]
        components = "\n".join(lines)
    else:
        components = "- （未注入任何组件能力；按纯本地仓库分析，缺失维度如实说明）"
    vars_ = {
        "project_name": project["name"],
        "repo_dir": str(projects.repo_dir(project["id"])),
        "shadow_dir": str(projects.ensure_shadow_repo(project["id"])),
        "date": time.strftime("%Y-%m-%d"),
        "components": components,
        **extra,
    }
    out = template
    for k, v in vars_.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def _ci_context(project: dict) -> dict:
    """同期 CI 构建上下文（FR-MGR-010 最小实现）：从 Jenkins job 拉 lastBuild
    注：supervisor 在宿主，ci.localhost 等域名走 127.0.0.1 + Host 头（容器不解析 *.localhost）"""
    ci_url = (project.get("ci_url") or "").strip().rstrip("/")
    if not ci_url:
        return {}
    try:
        from urllib.parse import urlparse
        u = urlparse(ci_url)
        host = u.hostname or ""
        base = "http://127.0.0.1" if host.endswith(".localhost") else f"{u.scheme}://{u.netloc}"
        headers = {"Host": host} if host.endswith(".localhost") else {}
        auth = (os.environ.get("JENKINS_ADMIN_ID", ""), os.environ.get("JENKINS_ADMIN_PASSWORD", ""))
        with httpx.Client(timeout=5, trust_env=False) as client:
            r = client.get(f"{base}{u.path}/lastBuild/api/json?tree=number,result,timestamp,url",
                           headers=headers, auth=auth if auth[1] else None)
        if r.status_code == 200:
            b = r.json()
            return {"job": ci_url, "build": b.get("number"), "result": b.get("result"),
                    "timestamp": b.get("timestamp")}
    except Exception:  # noqa: BLE001 - CI 上下文缺失不阻塞任务
        pass
    return {"job": ci_url, "error": "unreachable"}


def _runner_env() -> str:
    import platform
    from .. import __version__
    return f"{platform.system()} {platform.release()} / chronicler {__version__}"


def _file_hash(path: str) -> str:
    import hashlib
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]
    except OSError:
        return ""


def _harness_version(harness: dict) -> str:
    """尽力获取 harness CLI 版本（5s 超时，拿不到不阻塞）"""
    import shutil as _sh
    cmd = harness["command_template"].split("{")[0].strip().split()
    if not cmd or not _sh.which(cmd[0]):
        return ""
    try:
        r = subprocess.run([cmd[0], "--version"], capture_output=True, timeout=5,
                           encoding="utf-8", errors="replace")
        return (r.stdout or r.stderr).strip().splitlines()[0][:80] if (r.stdout or r.stderr) else ""
    except Exception:
        return ""


def _audit_push_failure(run: dict, e: Exception):
    audit("supervisor", "shadow.push_failed", f"run#{run['id']}", str(e)[:200])


def _classify_error(err: str) -> str:
    e = err.lower()
    if "超时" in err or "timeout" in e:
        return "超时"
    if any(k in e for k in ("429", "quota", "rate limit")):
        return "配额"
    if any(k in e for k in ("connection", "econn", "502", "503", "网络")):
        return "网络"
    if any(k in e for k in ("json", "parse", "解析")):
        return "解析"
    return "其他"


def trigger(project_id: int, task_type: str, actor: str, extra_prompt: str = "") -> dict:
    project = projects.get_project(project_id)
    if not projects.repo_dir(project_id).is_dir():
        projects.sync_project(project_id)  # 未 clone 则先同步

    overrides = project.get("overrides") or {}
    harness_name = overrides.get("harness") or os.environ.get("CHRONICLER_DEFAULT_HARNESS", "shell")
    harness = registry.get_harness(harness_name)
    if harness.get("session", "once") != "once":
        raise RuntimeError(f"harness {harness_name} 声明为持久会话，v1 暂不支持（ADR-0021 TBD）")

    template, prompt_version = registry.load_prompt(task_type)

    # A 段输入快照（§2.1.1，执行前冻结）
    snapshot = {
        "repo_head": projects.head_commit(project_id),
        "repo_dirty": projects.repo_dirty(project_id),
        "git_url": project["git_url"],
        "overrides": overrides,
        "harness_command": harness["command_template"],
        "harness_version": _harness_version(harness),
        "components": [{"name": c["name"], "skill": c["skill"],
                        "skill_hash": _file_hash(c["skill"])} for c in registry.injectable_components()],
        "ci_context": _ci_context(project),
    }
    run_id = execute(
        "INSERT INTO task_runs(project_id, task_type, status, harness, prompt_version,"
        " input_snapshot, created_by, started_at, runner_env)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (project_id, task_type, "queued", harness_name, prompt_version,
         dumps(snapshot), actor, time.time(), _runner_env()))
    # prompt 在 run_id 分配后渲染（需要 {{report_file}}/{{prompt_file}} 等运行路径变量）
    run_dir = Cfg.runs_dir() / str(run_id)
    prompt = _render_prompt(template, project, {
        "extra": extra_prompt,
        "report_file": str(run_dir / "report.md"),
        "prompt_file": str(run_dir / "prompt.md"),
    })
    threading.Thread(target=_run, args=(run_id, harness, prompt), daemon=True).start()
    return get_run(run_id)


def _run(run_id: int, harness: dict, prompt: str):
    run = get_run(run_id)
    repo = projects.repo_dir(run["project_id"])
    run_dir = Cfg.runs_dir() / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = run_dir / "prompt.md"
    report_file = run_dir / "report.md"
    log_file = run_dir / "run.log"
    prompt_file.write_text(prompt, encoding="utf-8")

    command = harness["command_template"].format(
        prompt_file=_q(str(prompt_file)),
        report_file=_q(str(report_file)),
        repo_dir=_q(str(repo)),
        shadow_dir=_q(str(projects.shadow_dir(run["project_id"]))))
    env = {**os.environ, **registry.resolve_env(harness.get("env"))}

    execute("UPDATE task_runs SET status='running', log_path=? WHERE id=?",
            (str(log_file), run_id))
    with _harness_lock(harness["name"]):
        try:
            stdin_data = prompt if harness.get("stdin_prompt") else None
            with open(log_file, "w", encoding="utf-8") as log:
                log.write(f"$ {command}\n\n")
                log.flush()
                proc = subprocess.run(command, shell=True, cwd=str(repo), env=env,
                                      input=stdin_data, text=bool(stdin_data),
                                      stdout=log, stderr=subprocess.STDOUT,
                                      timeout=harness.get("timeout_sec", 1800))
            artifacts = []
            if proc.returncode == 0:
                if report_file.is_file():
                    artifacts.append(_publish(run, report_file))
                _, shadow_arts = _commit_shadow(run)  # FR-MGR-013：shadow 库变更入库并记 artifact_commit
                artifacts.extend(shadow_arts)
            if proc.returncode == 0 and artifacts:
                execute("UPDATE task_runs SET status='success', artifacts=?, finished_at=? WHERE id=?",
                        (dumps(artifacts), time.time(), run_id))
            else:
                err = "" if proc.returncode == 0 else f"exit code {proc.returncode}"
                if not artifacts:
                    err = (err + "；" if err else "") + "未产出报告文件"
                execute("UPDATE task_runs SET status='failed', error=?, error_class=?, finished_at=? WHERE id=?",
                        (err, _classify_error(err), time.time(), run_id))
        except subprocess.TimeoutExpired:
            execute("UPDATE task_runs SET status='failed', error='超时', error_class='超时', finished_at=? WHERE id=?",
                    (time.time(), run_id))
        except Exception as e:  # noqa: BLE001 - 执行器兜底，错误必须落库
            err = f"{type(e).__name__}: {e}"[:500]
            execute("UPDATE task_runs SET status='failed', error=?, error_class=?, finished_at=? WHERE id=?",
                    (err, _classify_error(err), time.time(), run_id))


def _commit_shadow(run: dict) -> tuple[str | None, list[dict]]:
    """shadow 库收尾（FR-MGR-013）：有变更则提交，返回 (commit_sha, 新增产物清单)"""
    shadow = projects.shadow_dir(run["project_id"])
    if not shadow.is_dir():
        return None, []
    status = projects._git(["-C", str(shadow), "status", "--porcelain"]).stdout.strip()
    if not status:
        return None, []
    projects._git(["-C", str(shadow), "add", "-A"])
    projects._git(["-C", str(shadow), "-c", "user.name=chronicler", "-c",
                   "user.email=chronicler@localhost", "commit", "-m",
                   f"run#{run['id']} {run['task_type']}"])
    sha = projects._git(["-C", str(shadow), "rev-parse", "HEAD"]).stdout.strip()
    try:
        projects.push_shadow(run["project_id"])  # 指定了 shadow_repo 则同步到远端（如 Gitea）
    except Exception as e:  # noqa: BLE001 - 推送失败不影响本地档案
        _audit_push_failure(run, e)
    arts = []
    for line in status.splitlines():
        path = line[3:].strip()
        full = shadow / path
        arts.append({"kind": "knowhow" if "knowhow" in run["task_type"] else "shadow",
                     "path": str(full), "action": "created" if line.startswith("??") else "updated",
                     "size_bytes": full.stat().st_size if full.is_file() else 0, "commit": sha})
    return sha, arts


def _publish(run: dict, report_file) -> dict:
    """产物落盘并返回 artifact 记录（§2.1.1 C 段）。产物为 git 内容时补 commit（报告库 git 化在 M3）。"""
    dest_dir = Cfg.reports_dir() / str(run["project_id"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{run['task_type']}.md"
    dest.write_bytes(report_file.read_bytes())
    execute("UPDATE task_runs SET report_path=? WHERE id=?", (str(dest), run["id"]))
    return {"kind": "report", "path": str(dest), "action": "created",
            "size_bytes": dest.stat().st_size, "commit": None}


def get_run(run_id: int) -> dict:
    r = q1("SELECT t.*, p.name AS project_name FROM task_runs t"
           " JOIN projects p ON p.id=t.project_id WHERE t.id=?", (run_id,))
    if not r:
        raise HTTPException(status_code=404, detail="Run 不存在")
    r["input_snapshot"] = json.loads(r["input_snapshot"] or "{}")
    r["artifacts"] = json.loads(r.get("artifacts") or "[]")
    return r


def list_runs(project_id: int | None = None, limit: int = 50) -> list[dict]:
    if project_id:
        rows = q("SELECT * FROM task_runs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                 (project_id, limit))
    else:
        rows = q("SELECT * FROM task_runs ORDER BY id DESC LIMIT ?", (limit,))
    return rows
