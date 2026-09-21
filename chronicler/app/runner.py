"""任务执行器（M2 harness 执行器）：subprocess 一次性会话拉起 agent CLI（ADR-0021）

v1 边界：仅 once 会话（持久/resume 为 ADR-0021 标注的 TBD，后续版本）；
手动触发；日志落文件，前端轮询（SSE 留待后续）。
Run 档案契约见 docs/what/manager.md §2.1.1（A 输入快照 / B 执行过程 / C 产物清单）。

harness 命令形式可配置（FR-MGR-019）：prompt 经 {prompt_file} 文件或 stdin 管道
（stdin_prompt）传入；报告经 {report_file} 文件（report_mode=file，如 codex -o）或
stdout 捕获（report_mode=stdout，如 kimi --print）产出；cwd 可选工程仓库/shadow 库。
"""
import json
import hashlib
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

from fastapi import HTTPException

from . import change_detection, projects, registry
from .config import Cfg
from .db import audit, dumps, execute, q, q1
from .prompt_catalog import catalog
from .prompt_context import build_prompt_context, render_prompt
from .runtime import PROFILE

_harness_locks: dict[str, threading.Lock] = {}
_shadow_locks: dict[int, threading.Lock] = {}
STALE_QUEUE_GRACE_SEC = 600    # queued 超过 10 分钟仍未开始 = 悬挂
STALE_RUN_GRACE_SEC = 120      # running 超过 harness 超时后再宽限 2 分钟


def _harness_lock(name: str) -> threading.Lock:
    """同 harness 串行锁：kimi 等 CLI 有全局日志文件锁，并发实例会互抢（实测 WinError 32）"""
    if name not in _harness_locks:
        _harness_locks[name] = threading.Lock()
    return _harness_locks[name]


def _shadow_lock(project_id: int) -> threading.Lock:
    """同一 project_shadow 串行，锁覆盖 Agent 写入、提交和发布。"""
    if project_id not in _shadow_locks:
        _shadow_locks[project_id] = threading.Lock()
    return _shadow_locks[project_id]


def _q(path: str) -> str:
    """跨平台路径引号：Windows cmd 用双引号，POSIX 用 shlex（ADR-0020 多平台）"""
    return f'"{path}"' if os.name == "nt" else shlex.quote(path)


def _report_delivery(harness: dict, report_file: str) -> str:
    """按 harness 契约告诉 Agent 如何交付完整报告，避免 stdout/file 语义冲突。"""
    if harness.get("report_mode") == "stdout":
        return ("将完整 Markdown 作为最终响应输出到 stdout；不要只给摘要或文件路径。"
                "Supervisor 会捕获最终输出并保存为报告文件。")
    if "{report_file}" in harness.get("command_template", ""):
        return ("将完整 Markdown 作为最终响应；harness 会自动把最终响应保存到报告文件，"
                "无需在仓库中另建报告副本。")
    return f"使用文件写入能力将完整 Markdown 写入 `{report_file}`；不要只在最终响应中给摘要。"


def _decode_bytes(data: bytes) -> str:
    """按行解码：每行优先 UTF-8，单行失败回落本地编码（Windows 中文环境 GBK/cp936）。
    逐行回落避免文件里单个非 UTF-8 字节（或运行中读到半截写缓冲）把整份内容拖进
    GBK 重解导致整页乱码；日志/报告统一按 UTF-8 落盘。"""
    import locale
    fallback = locale.getpreferredencoding(False) or "utf-8"
    out = []
    for line in data.splitlines(keepends=True):
        try:
            out.append(line.decode("utf-8"))
        except UnicodeDecodeError:
            out.append(line.decode(fallback, errors="replace"))
    return "".join(out)


def _exec(command: str, cwd: str, env: dict, stdin_data: str | None,
          log_file, timeout_sec: int) -> tuple[int, str]:
    """执行 harness 命令：stdout 实时写入日志（供前端轮询），整份返回给调用方；
    stderr 合并进 stdout。子进程输出按 UTF-8（回落本地编码）解码后以 UTF-8 落盘
    （Windows GBK 坑，AGENTS.md 已登记）；并默认注入 PYTHONUTF8 强制 Python CLI 输出 UTF-8。"""
    env = dict(env)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.Popen(command, shell=True, cwd=cwd, env=env,
                            stdin=subprocess.PIPE if stdin_data is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    captured: list[str] = []

    def _drain():
        with open(log_file, "a", encoding="utf-8") as log:
            for raw in proc.stdout:
                line = _decode_bytes(raw)
                log.write(line)
                log.flush()
                captured.append(line)

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    if stdin_data is not None:
        try:
            proc.stdin.write(stdin_data.encode("utf-8"))
        except (BrokenPipeError, ValueError):
            pass
        finally:
            proc.stdin.close()
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=10)
        raise
    reader.join(timeout=10)
    return proc.returncode, "".join(captured)


def _ci_context(project: dict) -> dict:
    """同期 CI 构建上下文（FR-MGR-010）：由提供 hooks/ci.py 能力的组件完成（ADR-0025/0027）。"""
    ci_url = (project.get("ci_url") or "").strip().rstrip("/")
    if not ci_url:
        return {}
    try:
        from . import component_exec
        result = component_exec.run_capability("ci.py", ["last-build", ci_url], timeout=15)
        if result is None:
            return {"job": ci_url, "error": "no-ci-capability"}
        if result.get("ok"):
            return {"job": ci_url, "build": result.get("number"), "result": result.get("result"),
                    "timestamp": result.get("timestamp")}
        return {"job": ci_url, "error": result.get("error", "unreachable")}
    except Exception:  # noqa: BLE001 - CI 上下文缺失不阻塞任务
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
    if "悬挂" in err:
        return "悬挂"
    if "超时" in err or "timeout" in e:
        return "超时"
    if any(k in e for k in ("429", "quota", "rate limit")):
        return "配额"
    if any(k in e for k in ("connection", "econn", "502", "503", "网络")):
        return "网络"
    if any(k in e for k in ("json", "parse", "解析")):
        return "解析"
    return "其他"


def sweep_stale_runs(now: float | None = None) -> int:
    """状态悬挂检测（FR-MGR-005 执行过程兜底）：queued/running 超过阈值仍未结束
    （进程被中断 / supervisor 重启 / 执行线程死亡等未落库场景）→ 自动标记 failed，
    并写审计。由调度器每分钟调用。"""
    now = time.time() if now is None else now
    marked = 0
    for r in q("SELECT * FROM task_runs WHERE status IN ('queued','running')"):
        started = r.get("started_at") or now
        snap = json.loads(r.get("input_snapshot") or "{}")
        timeout = int(snap.get("harness_timeout") or 1800)
        if r["status"] == "queued":
            stale = now - started > STALE_QUEUE_GRACE_SEC
        else:
            stale = now - started > timeout + STALE_RUN_GRACE_SEC
        if not stale:
            continue
        n = execute("UPDATE task_runs SET status='failed', error=?, error_class='悬挂',"
                    " finished_at=? WHERE id=? AND status IN ('queued','running')",
                    ("状态悬挂：超过阈值仍未结束（进程可能被中断或 supervisor 重启），已自动标记失败",
                     now, r["id"]))
        if n:
            audit("supervisor", "run.stale", f"run#{r['id']}", f"{r['status']}->failed")
            marked += 1
    return marked


def trigger(project_id: int, task_type: str, actor: str, extra_prompt: str = "",
            prompt_override: str = "", cwd_override: str = "", harness_override: str = "",
            task_id: int | None = None, change_policy: str = "always", change_probes=None,
            allow_skip: bool = False, trigger_kind: str = "manual") -> dict:
    project = projects.get_project(project_id)
    task_spec = registry.get_task_type(task_type)
    projects.sync_project(project_id)

    overrides = project.get("overrides") or {}
    # harness 解析：任务定义覆盖 > 工程级覆盖 > 全局默认（FR-MGR-020）
    harness_name = harness_override or overrides.get("harness") or registry.get_default_harness()
    harness = registry.get_harness(harness_name)
    if harness.get("session", "once") != "once":
        raise RuntimeError(f"harness {harness_name} 声明为持久会话，v1 暂不支持（ADR-0021 TBD）")
    # 工作目录解析：任务定义覆盖（cwd_override）> harness 默认（cwd）> 工程仓库
    cwd = cwd_override if cwd_override in ("repo", "shadow") else harness.get("cwd", "repo")

    if prompt_override:
        # 工程级 prompt 覆盖（任务自带模板）；版本=内容 hash（FR-MGR-011）
        digest = hashlib.sha256(prompt_override.encode()).hexdigest()
        template, prompt_version = prompt_override, f"0.0.0+{digest[:8]}"
        prompt_hash = f"sha256:{digest}"
        prompt_name = f"{task_spec['prompt'] or 'custom'}-task-override"
    else:
        definition = catalog.resolve(task_spec["prompt"])
        template, prompt_version = definition.content, definition.version
        prompt_hash = definition.content_hash
        prompt_name = definition.name

    change = change_detection.capture(project_id, task_type, task_id, change_probes)
    ci_context = _ci_context(project)

    # A 段输入快照（§2.1.1，执行前冻结）
    snapshot = {
        "repo_head": projects.head_commit(project_id),
        "repo_dirty": projects.repo_dirty(project_id),
        "git_url": project["git_url"],
        "overrides": overrides,
        "harness_source": ("task" if harness_override
                           else ("project" if overrides.get("harness") else "global")),
        "harness_command": harness["command_template"],
        "harness_version": _harness_version(harness),
        "harness_timeout": int(harness.get("timeout_sec", 1800)),
        "cwd": cwd,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "task_mode": task_spec["mode"],
        "change_policy": change_policy,
        "publish_policy": registry.get_publish_policy(project),
        "shadow_base_commit": projects.shadow_head(project_id),
        "components": [{"name": c["name"], "skill": c["skill"],
                        "skill_hash": _file_hash(c["skill"])} for c in registry.injectable_components()],
        "ci_context": ci_context,
        **change,
    }
    started_at = time.time()
    run_id = execute(
        "INSERT INTO task_runs(task_id, project_id, task_type, status, trigger, harness, prompt_version,"
        " input_snapshot, created_by, started_at, runner_env)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, project_id, task_type, "queued", trigger_kind, harness_name, prompt_version,
         dumps(snapshot), actor, started_at, _runner_env()))
    # prompt 在 run_id 分配后渲染（需要 {{report_file}}/{{prompt_file}} 等运行路径变量）
    run_dir = Cfg.runs_dir() / str(run_id)
    report_file = str(run_dir / "report.md")
    prompt = render_prompt(template, build_prompt_context(
        run_id=run_id,
        project=project,
        task_type=task_type,
        task_mode=task_spec["mode"],
        task_id=task_id,
        trigger_kind=trigger_kind,
        actor=actor,
        started_at=started_at,
        harness=harness,
        harness_name=harness_name,
        cwd=cwd,
        change={**change, "formatted_context":
                change_detection.format_context(change["change_summary"])},
        ci_context=ci_context,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        run_dir=run_dir,
        report_file=report_file,
        prompt_file=str(run_dir / "prompt.md"),
        report_delivery=_report_delivery(harness, report_file),
        change_policy=change_policy,
        extra=extra_prompt,
    ))
    # A 段：渲染后 prompt 全文落库（任务列表可查看；文件副本 runs/<id>/prompt.md 同步保留）
    if PROFILE.persist_rendered_prompt:
        execute("UPDATE task_runs SET prompt_text=? WHERE id=?", (prompt, run_id))
    if allow_skip and change_detection.should_skip(change_policy, change["change_summary"]):
        execute("UPDATE task_runs SET status='skipped', error=?, error_class='无增量',"
                " finished_at=? WHERE id=?",
                (f"自动触发按 {change_policy} 策略跳过：无相关输入变化", time.time(), run_id))
        return get_run(run_id)
    threading.Thread(target=_run, args=(run_id, harness, prompt, cwd), daemon=True).start()
    return get_run(run_id)


def record_preflight_failure(task: dict, trigger_kind: str, error: Exception) -> dict:
    """自动触发进入 runner 前失败也保留 Run，避免调度器静默漏档。"""
    now = time.time()
    snapshot = {"change_policy": task.get("change_policy") or "always",
                "change_summary": {"state": "unknown", "repo_state": "unknown",
                                   "error": f"前置检查失败：{type(error).__name__}"}}
    run_id = execute(
        "INSERT INTO task_runs(task_id, project_id, task_type, status, trigger, harness,"
        " prompt_version, input_snapshot, error, error_class, created_by, started_at,"
        " finished_at, runner_env) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (task["id"], task["project_id"], task["task_type"], "failed", trigger_kind,
         task.get("harness") or "preflight", "", dumps(snapshot),
         "自动触发前置检查失败，详情见 supervisor 审计日志", "前置检查",
         trigger_kind, now, now, _runner_env()))
    audit("supervisor", "run.preflight_failed", f"run#{run_id}",
            f"{type(error).__name__}（原始异常文本未记录）")
    return get_run(run_id)


def _run(run_id: int, harness: dict, prompt: str, cwd: str = "repo"):
    run = get_run(run_id)
    repo = projects.repo_dir(run["project_id"])
    run_dir = Cfg.runs_dir() / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = run_dir / "prompt.md"
    report_file = run_dir / "report.md"
    log_file = run_dir / "run.log"
    if PROFILE.persist_rendered_prompt or not harness.get("stdin_prompt"):
        prompt_file.write_text(prompt, encoding="utf-8")
        try:
            prompt_file.chmod(0o600)
        except OSError:
            pass

    command = harness["command_template"].format(
        prompt_file=_q(str(prompt_file)),
        report_file=_q(str(report_file)),
        repo_dir=_q(str(repo)),
        shadow_dir=_q(str(projects.shadow_dir(run["project_id"]))))
    env = {**os.environ, **registry.resolve_env(harness.get("env"))}
    cwd_path = str(projects.shadow_dir(run["project_id"])) if cwd == "shadow" else str(repo)
    stdin_data = prompt if harness.get("stdin_prompt") else None
    capture_report = harness.get("report_mode") == "stdout"

    execute("UPDATE task_runs SET status='running', log_path=? WHERE id=?",
            (str(log_file), run_id))
    with _harness_lock(harness["name"]), _shadow_lock(run["project_id"]):
        try:
            publish_policy = run["input_snapshot"].get("publish_policy", "direct")
            if publish_policy != "direct":
                raise RuntimeError(f"尚未实现的发布策略：{publish_policy}")
            projects.prepare_shadow_direct(run["project_id"])
            with open(log_file, "w", encoding="utf-8") as log:
                log.write(f"$ {command}\n\n")
            returncode, stdout = _exec(command, cwd_path, env, stdin_data, log_file,
                                       int(harness.get("timeout_sec", 1800)))
            if capture_report and stdout.strip():
                report_file.write_text(stdout, encoding="utf-8", newline="\n")
            artifacts = []
            # 产出契约优先于退出码（kimi 等 CLI 收尾阶段会误报非零）：有产物即成功
            if returncode == 0 or report_file.is_file():
                if report_file.is_file():
                    artifacts.append(_publish(run, report_file))
                sha, shadow_arts, publication = _commit_shadow(run, publish_policy)
                if sha:
                    for a in artifacts:
                        a["commit"] = a.get("commit") or sha
                artifacts.extend(shadow_arts)
            if artifacts:
                warn = "" if returncode == 0 else f"（harness 退出码 {returncode}，产物已在，判成功）"
                execute("UPDATE task_runs SET status='success', artifacts=?, publication=?, error=?,"
                    " finished_at=? WHERE id=?",
                    (dumps(artifacts), dumps(publication), warn, time.time(), run_id))
            else:
                err = "" if returncode == 0 else f"exit code {returncode}"
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
        finally:
            if not PROFILE.persist_rendered_prompt and prompt_file.is_file():
                prompt_file.unlink(missing_ok=True)


def _commit_shadow(run: dict, publish_policy: str) -> tuple[str | None, list[dict], dict]:
    """由 Chronicler 提交并发布 shadow 变更；首版实现 direct 到 main。"""
    shadow = projects.shadow_dir(run["project_id"])
    publication = {
        "mode": publish_policy,
        "base_commit": run.get("input_snapshot", {}).get("shadow_base_commit", ""),
        "branch": projects.SHADOW_MAIN_BRANCH,
        "push_status": "pending",
        "pr_number": None,
        "pr_url": "",
        "publish_error": "",
    }
    if not shadow.is_dir():
        publication["push_status"] = "failed"
        publication["publish_error"] = "shadow 仓不存在"
        return None, [], publication
    status = projects._git(["-C", str(shadow), "status", "--porcelain"]).stdout.strip()
    if not status:
        publication["push_status"] = "unchanged"
        return None, [], publication
    projects._git(["-C", str(shadow), "add", "-A"])
    committed = projects._git(["-C", str(shadow), "-c", "user.name=chronicler", "-c",
                               "user.email=chronicler@localhost", "commit", "-m",
                               f"run#{run['id']} {run['task_type']}"])
    if committed.returncode != 0:
        raise RuntimeError(f"shadow 提交失败：{committed.stderr.strip()[:300]}")
    sha = projects._git(["-C", str(shadow), "rev-parse", "HEAD"]).stdout.strip()
    pushed = False
    try:
        pushed = bool(projects.push_shadow(run["project_id"], projects.SHADOW_MAIN_BRANCH))
        publication["push_status"] = "pushed" if pushed else "local"
    except Exception as e:  # noqa: BLE001
        _audit_push_failure(run, e)
        publication["push_status"] = "failed"
        publication["publish_error"] = str(e)[:500]
    arts = []
    for line in status.splitlines():
        path = line[3:].strip()
        full = shadow / path
        normalized = path.replace("\\", "/")
        kind = ("knowhow" if normalized.startswith("know-how/") else
            "doc" if normalized.startswith("docs/") else "shadow")
        arts.append({"kind": kind,
                     "path": str(full), "action": "created" if line.startswith("??") else "updated",
                     "size_bytes": full.stat().st_size if full.is_file() else 0,
                     "commit": sha, "pushed": pushed})
    return sha, arts, publication


def _publish(run: dict, report_file) -> dict:
    """报告写入 shadow 仓（ADR-0028）。组织规则（用户定）：状态/周期类按时间序，
    分析/洞察类按结构（稳定文件名原地更新，历史交给 git）。"""
    shadow = projects.ensure_shadow_repo(run["project_id"])
    if run["task_type"] in ("daily-report",):
        dest_dir = shadow / "reports" / "daily"
        name = f"{time.strftime('%Y-%m-%d')}.md"
    else:
        dest_dir = shadow / "reports"
        name = f"{run['task_type']}.md"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    action = "updated" if dest.exists() else "created"
    # 统一按 UTF-8 落盘（报告可能由 GBK 输出的 CLI 生成，先解码归一）
    dest.write_text(_decode_bytes(report_file.read_bytes()), encoding="utf-8", newline="\n")
    execute("UPDATE task_runs SET report_path=? WHERE id=?", (str(dest), run["id"]))
    return {"kind": "report", "path": str(dest), "action": action,
            "size_bytes": dest.stat().st_size, "commit": None}


# 注：mkdocs 只经挂载读 data/public/reports（见 compose），supervisor 不写本仓。


def get_run(run_id: int) -> dict:
    r = q1("SELECT t.*, p.name AS project_name FROM task_runs t"
           " JOIN projects p ON p.id=t.project_id WHERE t.id=?", (run_id,))
    if not r:
        raise HTTPException(status_code=404, detail="Run 不存在")
    r["input_snapshot"] = json.loads(r["input_snapshot"] or "{}")
    r["artifacts"] = json.loads(r.get("artifacts") or "[]")
    r["publication"] = json.loads(r.get("publication") or "{}")
    return r


def list_runs(project_id: int | None = None, limit: int = 50) -> list[dict]:
    cols = ("id, task_id, project_id, task_type, status, trigger, harness, prompt_version, input_snapshot, log_path,"
            " report_path, error, error_class, runner_env, artifacts, publication, created_by,"
            " started_at, finished_at")
    if project_id:
        rows = q(f"SELECT {cols} FROM task_runs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                 (project_id, limit))
    else:
        rows = q(f"SELECT {cols} FROM task_runs ORDER BY id DESC LIMIT ?", (limit,))
    for row in rows:
        try:
            snapshot = json.loads(row.pop("input_snapshot") or "{}")
        except json.JSONDecodeError:
            snapshot = {}
        row["baseline_run_id"] = snapshot.get("baseline_run_id")
        row["change_summary"] = snapshot.get("change_summary") or {}
        row["repo_head"] = snapshot.get("repo_head", "")
    return rows
