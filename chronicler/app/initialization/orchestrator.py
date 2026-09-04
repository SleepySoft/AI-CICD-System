"""持久化初始化运行与组件 DAG 批量执行。"""
import json
import hashlib
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docker

from .. import db
from ..auth import hash_password
from ..runtime import component_python
from ..tools import ensure_running, get_tool
from . import catalog, config_store, store

_workers: dict[int, threading.Thread] = {}


def save_plan(plan: dict) -> dict:
    plan_id = store.execute("""INSERT INTO setup_plans
        (draft_revision,environment_fingerprint,plan_hash,plan_json,created_at)
        VALUES(?,?,?,?,?)""", (plan["draft_revision"], plan["environment_fingerprint"],
                               plan["plan_hash"], json.dumps(plan, ensure_ascii=False), time.time()))
    return {**plan, "id": plan_id}


def get_plan(plan_id: int) -> dict | None:
    row = store.one("SELECT * FROM setup_plans WHERE id=?", (plan_id,))
    if not row:
        return None
    return {**json.loads(row["plan_json"]), "id": row["id"], "confirmed_at": row["confirmed_at"]}


def create_run(plan_id: int) -> int:
    plan = get_plan(plan_id)
    if not plan:
        raise ValueError("计划不存在")
    draft = store.get_draft()
    if plan["draft_revision"] != draft["revision"]:
        raise ValueError("配置已变化，请重新生成并确认计划")
    if plan["catalog_revision"] != catalog.revision(catalog.load()):
        raise ValueError("组件声明已变化，请重新生成并确认计划")
    now = time.time()
    with store.transaction() as conn:
        if conn.execute("SELECT id FROM setup_runs WHERE status='running'").fetchone():
            raise ValueError("已有初始化任务正在运行")
        run_id = conn.execute("INSERT INTO setup_runs(plan_id,status,started_at) VALUES(?,'running',?)",
                              (plan_id, now)).lastrowid
        for ordinal, action in enumerate(plan["actions"]):
            input_hash = hashlib.sha256(json.dumps(
                {"plan": plan["plan_hash"], "action": action}, sort_keys=True).encode()).hexdigest()
            conn.execute("""INSERT INTO setup_steps
                (run_id,component,phase,ordinal,status,input_hash) VALUES(?,?,?,?, 'pending',?)""",
                (run_id, action["component"], action["phase"], ordinal, input_hash))
        conn.execute("UPDATE setup_plans SET confirmed_at=? WHERE id=?", (now, plan_id))
        conn.execute("""UPDATE installation SET lifecycle='configuring',active_run_id=?,updated_at=?
                     WHERE id=1""", (run_id, now))
    worker = threading.Thread(target=_run, args=(run_id, plan), daemon=True)
    _workers[run_id] = worker
    worker.start()
    return run_id


def _event(run_id: int, level: str, event_type: str, message: str, step_id: int | None = None):
    store.add_event(run_id, level, event_type, message, step_id)


def _step(run_id: int, component: str, phase: str) -> dict:
    return store.one("SELECT * FROM setup_steps WHERE run_id=? AND component=? AND phase=?",
                     (run_id, component, phase))


def _mark(step: dict, status: str, error: str = ""):
    now = time.time()
    store.execute("""UPDATE setup_steps SET status=?,attempt=attempt+CASE WHEN ?='running' THEN 1 ELSE 0 END,
        started_at=COALESCE(started_at,?),finished_at=?,error_summary=? WHERE id=?""",
        (status, status, now, now if status in {"success", "failed", "skipped", "blocked"} else None,
         config_store.redact(error)[:500], step["id"]))


def _wait_ready(name: str, timeout: int):
    client = docker.from_env()
    tool = get_tool(name)
    deadline = time.time() + timeout
    while time.time() < deadline:
        container = client.containers.get(tool["container"])
        container.reload()
        health = (container.attrs.get("State", {}).get("Health") or {}).get("Status")
        if container.status == "running" and health in (None, "healthy"):
            return
        if health == "unhealthy":
            raise RuntimeError("容器健康检查失败")
        time.sleep(2)
    raise TimeoutError(f"等待 {name} 就绪超时")


def _hook(name: str, action: str):
    entries = catalog.load()
    entry = entries[name]["component"]
    hook = entry.get("initialize_hook")
    if not hook:
        return
    path = Path(entry["_dir"]) / hook
    dependencies, queue = {name}, [name]
    while queue:
        current = queue.pop()
        for dependency in entries[current]["component"].get("depends_on", []):
            if dependency not in dependencies:
                dependencies.add(dependency)
                queue.append(dependency)
    field_keys = {field["key"] for component in dependencies
                  for field in entries[component]["component"].get("fields", [])}
    base_keys = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP",
                 "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY",
                 "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "BASE_DOMAIN"}
    env = {key: value for key, value in os.environ.items() if key.upper() in base_keys | field_keys}
    env["CHRONICLER_COMPONENT_CONTAINER"] = get_tool(name).get("container", "")
    for dependency in dependencies - {name}:
        env[f"CHRONICLER_DEPENDENCY_{dependency.upper().replace('-', '_')}_CONTAINER"] = \
            get_tool(dependency).get("container", "")
    proc = subprocess.run([component_python(), str(path), action], cwd=str(path.parent.parent),
                          env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=300)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout or "初始化 hook 失败")[-500:])


def _ensure_admin():
    db.init()
    username, password = config_store.consume_admin()
    existing = db.q1("SELECT id,role FROM users WHERE username=?", (username,))
    if existing and existing["role"] != "admin":
        raise ValueError("同名普通用户已存在，不能覆盖")
    if existing:
        return
    if not password or len(password) < 8:
        raise ValueError("管理员密码至少 8 位，请返回配置步骤重新输入")
    db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'admin',?)",
               (username, hash_password(password), time.time()))


def _run_action(run_id: int, plan: dict, component: str, phase: str):
    entries = catalog.load()
    if phase == "persist":
        config_store.persist(plan["values"], entries)
        _ensure_admin()
    elif phase == "admin":
        _ensure_admin()
    elif phase == "deploy":
        action = ensure_running(get_tool(component))
        if action == "error":
            raise RuntimeError("组件部署失败，请查看 Docker 日志")
    elif phase == "ready":
        timeout = int(entries[component]["component"].get("readiness", {}).get("timeout_sec", 600))
        _wait_ready(component, timeout)
    elif phase == "configure":
        _hook(component, "apply")
    elif phase == "verify":
        _hook(component, "check")
    elif phase == "finalize":
        return


def _execute_step(run_id: int, plan: dict, step: dict):
    if step["status"] in {"success", "skipped"}:
        return
    if store.one("SELECT cancel_requested FROM setup_runs WHERE id=?", (run_id,))["cancel_requested"]:
        raise InterruptedError("用户已请求取消")
    _mark(step, "running")
    _event(run_id, "info", "step.running",
           f"开始：{step['component'] + ' / ' if step['component'] else ''}{step['phase']}", step["id"])
    try:
        _run_action(run_id, plan, step["component"], step["phase"])
        _mark(step, "success")
        _event(run_id, "success", "step.success", "完成", step["id"])
    except Exception as exc:
        safe_error = config_store.redact(exc)
        _mark(step, "failed", safe_error)
        store.execute("UPDATE setup_steps SET error_class=? WHERE id=?",
                      (type(exc).__name__, step["id"]))
        _event(run_id, "error", "step.failed", safe_error, step["id"])
        raise


def _component_sequence(run_id: int, plan: dict, name: str):
    try:
        for phase in ("deploy", "ready", "configure", "verify"):
            _execute_step(run_id, plan, _step(run_id, name, phase))
    finally:
        db.close()


def _block_component(run_id: int, name: str, reason: str):
    for phase in ("deploy", "ready", "configure", "verify"):
        step = _step(run_id, name, phase)
        if step and step["status"] == "pending":
            _mark(step, "blocked", reason)


def _run(run_id: int, plan: dict):
    try:
        _execute_step(run_id, plan, _step(run_id, "", "persist"))
        _execute_step(run_id, plan, _step(run_id, "", "admin"))

        dependencies = {item["name"]: set(item["depends_on"]) for item in plan["components"]}
        pending, completed, failed = set(dependencies), set(), set()
        while pending:
            blocked = {name for name in pending if dependencies[name] & failed}
            for name in blocked:
                _block_component(run_id, name, "前置组件失败")
            pending -= blocked
            failed |= blocked
            ready = sorted(name for name in pending if dependencies[name] <= completed)
            if not ready:
                if pending:
                    raise RuntimeError("组件依赖无法继续执行")
                break
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="setup") as pool:
                futures = {pool.submit(_component_sequence, run_id, plan, name): name for name in ready}
                for future in as_completed(futures):
                    name = futures[future]
                    pending.discard(name)
                    try:
                        future.result()
                        completed.add(name)
                    except InterruptedError:
                        raise
                    except Exception:
                        failed.add(name)
        if failed:
            raise RuntimeError("部分组件失败；可修复后重试同一计划")

        _execute_step(run_id, plan, _step(run_id, "", "finalize"))
        now = time.time()
        with store.transaction() as conn:
            conn.execute("UPDATE setup_runs SET status='success',finished_at=? WHERE id=?", (now, run_id))
            conn.execute("""UPDATE installation SET lifecycle='ready',bootstrap_closed_at=?,
                         active_run_id=NULL,completed_plan_hash=?,updated_at=? WHERE id=1""",
                         (now, plan["plan_hash"], now))
        _event(run_id, "success", "run.success", "初始化完成，请重启 Chronicler 进入正常模式")
        config_store.clear()
    except InterruptedError as exc:
        now = time.time()
        with store.transaction() as conn:
            conn.execute("UPDATE setup_runs SET status='canceled',finished_at=? WHERE id=?", (now, run_id))
            conn.execute("UPDATE installation SET active_run_id=NULL,updated_at=? WHERE id=1", (now,))
        _event(run_id, "warning", "run.canceled", str(exc))
    except Exception as exc:
        store.execute("UPDATE setup_runs SET status='failed',finished_at=? WHERE id=?", (time.time(), run_id))
        store.execute("UPDATE installation SET active_run_id=NULL,updated_at=? WHERE id=1", (time.time(),))
        _event(run_id, "error", "run.failed", config_store.redact(exc))
    finally:
        db.close()


def run_status(run_id: int) -> dict | None:
    run = store.one("SELECT * FROM setup_runs WHERE id=?", (run_id,))
    if not run:
        return None
    run["steps"] = store.all_("SELECT * FROM setup_steps WHERE run_id=? ORDER BY ordinal", (run_id,))
    run["events"] = store.all_("SELECT * FROM setup_events WHERE run_id=? ORDER BY id", (run_id,))
    return run


def cancel(run_id: int):
    store.execute("UPDATE setup_runs SET cancel_requested=1 WHERE id=? AND status='running'", (run_id,))


def retry(run_id: int) -> int:
    """在同一运行上仅重置失败/阻塞步骤，保留成功步骤和输入摘要。"""
    now = time.time()
    with store.transaction() as conn:
        run = conn.execute("SELECT * FROM setup_runs WHERE id=?", (run_id,)).fetchone()
        if not run or run["status"] not in {"failed", "canceled"}:
            raise ValueError("只有失败或取消的运行可以重试")
        if conn.execute("SELECT id FROM setup_runs WHERE status='running'").fetchone():
            raise ValueError("已有初始化任务正在运行")
        conn.execute("""UPDATE setup_steps SET status='pending',error_class='',error_summary='',
                     started_at=NULL,finished_at=NULL WHERE run_id=? AND status NOT IN ('success','skipped')""",
                     (run_id,))
        conn.execute("UPDATE setup_runs SET status='running',cancel_requested=0,finished_at=NULL WHERE id=?",
                     (run_id,))
        conn.execute("UPDATE installation SET lifecycle='configuring',active_run_id=?,updated_at=? WHERE id=1",
                     (run_id, now))
    plan = get_plan(run["plan_id"])
    config_store.load_environment(catalog.load())
    worker = threading.Thread(target=_run, args=(run_id, plan), daemon=True)
    _workers[run_id] = worker
    worker.start()
    return run_id


def resume_active():
    """进程重启后接管活动运行；已成功步骤由 _execute_step 跳过。"""
    inst = store.installation()
    run_id = inst.get("active_run_id") if inst else None
    if not run_id or run_id in _workers and _workers[run_id].is_alive():
        return
    run = store.one("SELECT * FROM setup_runs WHERE id=? AND status='running'", (run_id,))
    if not run:
        return
    plan = get_plan(run["plan_id"])
    if not plan:
        store.execute("UPDATE setup_runs SET status='failed',finished_at=? WHERE id=?", (time.time(), run_id))
        return
    config_store.load_environment(catalog.load())
    worker = threading.Thread(target=_run, args=(run_id, plan), daemon=True)
    _workers[run_id] = worker
    worker.start()


def history() -> list[dict]:
    return store.all_("""SELECT r.id,r.plan_id,r.status,r.started_at,r.finished_at,p.plan_hash
                       FROM setup_runs r JOIN setup_plans p ON p.id=r.plan_id ORDER BY r.id DESC LIMIT 50""")