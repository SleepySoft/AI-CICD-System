"""任务定义与调度（FR-MGR-004 前置形态）：工程挂任务，手动/cron 触发，可停用不删配置

任务 = 工程 + task_type（对应 prompts/<task_type>.md）+ 可选 prompt 覆盖 + 触发配置。
webhook/联动触发为预留字段，本次不实装。
"""
import threading
import time

from . import projects, runner
from .db import execute, q, q1

# 预置任务类型（新建工程默认全挂上）：对应 chronicler/prompts/*.md
PRESET_TASKS = ["daily-report", "code-insight", "deviation-analysis",
                "compliance-check", "knowhow-distill", "structured-docs"]


def create_task(project_id: int, name: str, task_type: str, schedule_cron: str = "",
                enabled: bool = True, cwd: str = "", harness: str = "") -> dict:
    projects.get_project(project_id)
    if q1("SELECT id FROM task_defs WHERE project_id=? AND task_type=?",
          (project_id, task_type)):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="该工程已有同类型任务")
    tid = execute(
        "INSERT INTO task_defs(project_id, name, task_type, harness, cwd, schedule_cron, enabled, created_at)"
        " VALUES (?,?,?,?,?,?,?,strftime('%s','now'))",
        (project_id, name, task_type, harness, cwd, schedule_cron, 1 if enabled else 0))
    return get_task(tid)


def create_preset_tasks(project_id: int):
    """工程默认挂预置任务（幂等，启动时对存量工程也会补齐；全部仅手动触发）"""
    for tt in PRESET_TASKS:
        try:
            create_task(project_id, f"{tt}（预置）", tt)
        except Exception:
            pass


def backfill_preset_tasks():
    """启动钩子：给所有缺预置任务的存量工程补齐（幂等）"""
    from .db import q
    for p in q("SELECT id FROM projects"):
        create_preset_tasks(p["id"])


def get_task(tid: int) -> dict:
    t = q1("SELECT * FROM task_defs WHERE id=?", (tid,))
    if not t:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="任务不存在")
    return t


def list_tasks(project_id: int | None = None) -> list[dict]:
    if project_id:
        return q("SELECT * FROM task_defs WHERE project_id=? ORDER BY id", (project_id,))
    return q("SELECT * FROM task_defs ORDER BY project_id, id")


def update_task(tid: int, fields: dict) -> dict:
    get_task(tid)
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "schedule_cron", "webhook", "enabled", "prompt_override", "cwd", "harness")}
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        execute(f"UPDATE task_defs SET {sets} WHERE id=?", (*allowed.values(), tid))
    return get_task(tid)


def delete_task(tid: int):
    t = get_task(tid)
    execute("DELETE FROM task_defs WHERE id=?", (tid,))
    return {"ok": True, "name": t["name"]}


def delete_project_tasks(project_id: int):
    execute("DELETE FROM task_defs WHERE project_id=?", (project_id,))


def trigger_task(tid: int, actor: str, extra_prompt: str = "") -> dict:
    t = get_task(tid)
    # prompt 覆盖：工程任务自定义 > 全局模板（版本化 hash 由 runner 记录）
    if t.get("prompt_override"):
        return runner.trigger(t["project_id"], t["task_type"], actor, extra_prompt,
                              prompt_override=t["prompt_override"], cwd_override=t.get("cwd", ""),
                              harness_override=t.get("harness", ""))
    return runner.trigger(t["project_id"], t["task_type"], actor, extra_prompt,
                          cwd_override=t.get("cwd", ""), harness_override=t.get("harness", ""))


# ---------- cron 调度（简单轮询，每分钟） ----------

_scheduler_started = False


def scheduler_tick():
    """每分钟被调用一次：状态悬挂扫描 + 到点且 enabled 的任务触发"""
    import croniter
    try:
        runner.sweep_stale_runs()
    except Exception:
        pass  # 悬挂扫描失败不影响调度
    now = time.time()
    for t in q("SELECT * FROM task_defs WHERE enabled=1 AND schedule_cron != ''"):
        try:
            cron = croniter.croniter(t["schedule_cron"], now - 120)
            prev_fire = cron.get_prev()
            # 上次应触发时刻在 90 秒内 → 触发（容忍调度抖动）
            if prev_fire and now - prev_fire < 90:
                last = q1("SELECT MAX(started_at) AS last FROM task_runs"
                          " WHERE project_id=? AND task_type=? AND trigger='cron'",
                          (t["project_id"], t["task_type"]))
                if last and last["last"] and now - last["last"] < 90:
                    continue  # 刚跑过
                runner.trigger(t["project_id"], t["task_type"], "cron",
                               cwd_override=t.get("cwd", ""), harness_override=t.get("harness", ""))
        except Exception:
            continue  # cron 表达式非法等，单任务失败不影响调度


def start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def loop():
        while True:
            try:
                scheduler_tick()
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="chronicler-scheduler").start()
