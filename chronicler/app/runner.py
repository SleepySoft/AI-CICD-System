"""任务执行器（M2 harness 执行器）：subprocess 一次性会话拉起 agent CLI（ADR-0021）

v1 边界：仅 once 会话（持久/resume 为 ADR-0021 标注的 TBD，后续版本）；
手动触发；日志落文件，前端轮询（SSE 留待后续）。
"""
import json
import os
import shlex
import subprocess
import threading
import time

from fastapi import HTTPException

from . import projects, registry
from .config import Cfg
from .db import dumps, execute, q, q1


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
        "date": time.strftime("%Y-%m-%d"),
        "components": components,
        **extra,
    }
    out = template
    for k, v in vars_.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


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
    prompt = _render_prompt(template, project, {"extra": extra_prompt})

    run_id = execute(
        "INSERT INTO task_runs(project_id, task_type, status, harness, prompt_version,"
        " input_snapshot, created_by, started_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (project_id, task_type, "queued", harness_name, prompt_version,
         dumps({"repo_head": projects.head_commit(project_id), "git_url": project["git_url"],
                "overrides": overrides,
                "components": [c["name"] for c in registry.injectable_components()]}),
         actor, time.time()))
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
        repo_dir=_q(str(repo)))
    env = {**os.environ, **registry.resolve_env(harness.get("env"))}

    execute("UPDATE task_runs SET status='running', log_path=? WHERE id=?",
            (str(log_file), run_id))
    t0 = time.time()
    try:
        with open(log_file, "w", encoding="utf-8") as log:
            log.write(f"$ {command}\n\n")
            log.flush()
            proc = subprocess.run(command, shell=True, cwd=str(repo), env=env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  timeout=harness.get("timeout_sec", 1800))
        if proc.returncode == 0 and report_file.is_file():
            _publish(run, report_file)
            execute("UPDATE task_runs SET status='success', finished_at=? WHERE id=?",
                    (time.time(), run_id))
        else:
            err = "" if proc.returncode == 0 else f"exit code {proc.returncode}"
            if not report_file.is_file():
                err = (err + "；" if err else "") + "未产出报告文件"
            execute("UPDATE task_runs SET status='failed', error=?, finished_at=? WHERE id=?",
                    (err, time.time(), run_id))
    except subprocess.TimeoutExpired:
        execute("UPDATE task_runs SET status='failed', error='超时', finished_at=? WHERE id=?",
                (time.time(), run_id))
    except Exception as e:  # noqa: BLE001 - 执行器兜底，错误必须落库
        execute("UPDATE task_runs SET status='failed', error=?, finished_at=? WHERE id=?",
                (f"{type(e).__name__}: {e}"[:500], time.time(), run_id))


def _publish(run: dict, report_file):
    dest_dir = Cfg.reports_dir() / str(run["project_id"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{run['task_type']}.md"
    dest.write_bytes(report_file.read_bytes())
    execute("UPDATE task_runs SET report_path=? WHERE id=?", (str(dest), run["id"]))


def get_run(run_id: int) -> dict:
    r = q1("SELECT t.*, p.name AS project_name FROM task_runs t"
           " JOIN projects p ON p.id=t.project_id WHERE t.id=?", (run_id,))
    if not r:
        raise HTTPException(status_code=404, detail="Run 不存在")
    r["input_snapshot"] = json.loads(r["input_snapshot"] or "{}")
    return r


def list_runs(project_id: int | None = None, limit: int = 50) -> list[dict]:
    if project_id:
        rows = q("SELECT * FROM task_runs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                 (project_id, limit))
    else:
        rows = q("SELECT * FROM task_runs ORDER BY id DESC LIMIT ?", (limit,))
    return rows
