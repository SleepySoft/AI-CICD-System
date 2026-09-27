"""任务接收、重复请求、锁等待、失败与调度的链路回归；不运行真实 agent。"""
import concurrent.futures
import io
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from chronicler.app import db, projects, runner, tasks
from chronicler.app.auth import current_user, require_admin
from chronicler.app.config import Cfg
from chronicler.app.routers import runs as runs_router, tasks as tasks_router


class HarnessTimeoutTest(unittest.TestCase):
    def test_windows_timeout_waits_for_exit_and_drain_when_tree_kill_fails(self):
        for stop_code in (0, 1):
            with self.subTest(stop_code=stop_code), tempfile.TemporaryDirectory() as temporary:
                log = Path(temporary) / "run.log"
                process = Mock(pid=123, stdout=io.BytesIO(b"started\n"), stdin=io.BytesIO())
                process.wait.side_effect = [subprocess.TimeoutExpired("harness", 1), 0]
                process.poll.return_value = None
                threads = []
                def make_thread(**kwargs):
                    thread = Mock()
                    threads.append(thread)
                    return thread
                with patch.object(runner.os, "name", "nt"), \
                     patch.object(runner.subprocess, "Popen", return_value=process), \
                     patch.object(runner.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True), \
                     patch.object(runner.subprocess, "run", return_value=Mock(returncode=stop_code)) as stop, \
                     patch.object(runner.threading, "Thread", side_effect=make_thread):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        runner._exec("harness", temporary, {}, "large prompt", log, 1)
                stop.assert_called_once_with(["taskkill", "/PID", "123", "/T", "/F"],
                                             capture_output=True, timeout=30)
                self.assertEqual(process.wait.call_count, 2)
                threads[0].join.assert_called_once_with()
                threads[1].join.assert_called_once_with(timeout=10)
                self.assertTrue(process.stdout.closed)
                if stop_code:
                    self.assertIn("等待进程退出", log.read_text(encoding="utf-8"))


class TaskLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(Cfg, "DATA", root / "private"),
                        patch.object(Cfg, "PUBLIC", root / "public"),
                        patch.object(Cfg, "WORKSPACE", root / "workspace")]
        for item in self.patches:
            item.start()
        db.close()
        self.connections = set()
        original_db = db.db
        def tracked_db():
            connection = original_db()
            self.connections.add(connection)
            return connection
        self.connection_patch = patch.object(db, "db", side_effect=tracked_db)
        self.connection_patch.start()
        db.init()
        self.project = projects.create_project("sample", "https://example.invalid/repo.git")
        self.task = tasks.create_task(self.project["id"], "报告", "operational_reporter", harness="dummy")
        self.gates = []
        self.started = threading.Event()
        self.gate = threading.Event()
        self.gates.append(self.gate)
        self.prepared_ids = []
        self.prepare_patch = patch.object(runner, "_prepare_run", side_effect=self.prepare)
        self.run_patch = patch.object(runner, "_run", side_effect=self.complete)
        self.prepare_patch.start()
        self.run_patch.start()

    def prepare(self, run_id, *args, **kwargs):
        self.prepared_ids.append(run_id)
        self.started.set()
        if not self.gate.wait(5):
            raise TimeoutError("test gate")
        return "prompt", "repo"

    def complete(self, run_id, *args):
        db.execute("UPDATE task_runs SET status='success', finished_at=? WHERE id=?", (time.time(), run_id))

    def join_workers(self):
        with runner._workers_guard:
            workers = list(runner._workers.values())
        for worker in workers:
            worker.join(6)
            self.assertFalse(worker.is_alive(), "worker must exit before fixture cleanup")

    def tearDown(self):
        for event in self.gates:
            event.set()
        self.join_workers()
        self.run_patch.stop()
        self.prepare_patch.stop()
        db.close()
        for connection in self.connections:
            connection.close()
        self.connection_patch.stop()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def trigger(self, key="", task_type="operational_reporter"):
        return runner.trigger(self.project["id"], task_type, "admin",
                              harness_override="dummy", request_key=key)

    def test_run_is_visible_before_slow_preflight_finishes(self):
        run = self.trigger("slow")
        self.assertTrue(self.started.wait(2))
        visible = runner.list_runs()[0]
        self.assertEqual(run["id"], visible["id"])
        self.assertEqual("queued", visible["status"])
        self.assertEqual("preparing", visible["phase"])
        self.assertIsNone(visible["started_at"])
        self.assertTrue(visible["queued_at"])

    def test_concurrent_retry_uses_one_run_even_after_completion(self):
        def submit():
            try:
                return self.trigger("same-click")["id"]
            finally:
                db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda _: submit(), range(8)))
        self.assertEqual(1, len(set(ids)))
        self.gate.set()
        self.join_workers()
        again = self.trigger("same-click")
        self.assertEqual(ids[0], again["id"])
        self.assertTrue(again["reused"])
        self.assertEqual(1, len(runner.list_runs()))
        self.assertEqual([ids[0]], self.prepared_ids)

    def test_different_keys_and_entrypoints_cannot_duplicate_active_task(self):
        run = tasks.trigger_task(self.task["id"], "admin", request_key="task-route")
        with self.assertRaises(HTTPException) as ctx:
            self.trigger("direct-route")
        self.assertEqual(409, ctx.exception.status_code)
        self.assertIn(str(run["id"]), ctx.exception.detail)
        self.assertEqual(1, len(runner.list_runs()))

    def test_key_cannot_be_reused_for_different_parameters(self):
        self.trigger("fixed-key")
        with self.assertRaises(HTTPException) as ctx:
            self.trigger("fixed-key", "project_cognitive_maintainer")
        self.assertEqual(409, ctx.exception.status_code)
        self.assertEqual(1, len(runner.list_runs()))

    def test_waiting_workers_are_not_running_or_stale(self):
        first = self.trigger("first")
        self.assertTrue(self.started.wait(2))
        second = self.trigger("second", "project_cognitive_maintainer")
        waiting = runner.get_run(second["id"])
        self.assertEqual("queued", waiting["status"])
        self.assertEqual("waiting", waiting["input_snapshot"]["phase"])
        self.assertIsNone(waiting["started_at"])
        self.assertEqual(0, runner.sweep_stale_runs(time.time() + 10000))
        self.assertEqual([first["id"]], self.prepared_ids)

    def test_active_worktree_rejects_sync_reset_and_delays_preview_snapshot(self):
        self.trigger("worktree")
        self.assertTrue(self.started.wait(2))
        for operation in (projects.sync_project, projects.reset_clone):
            with self.assertRaises(HTTPException) as ctx:
                operation(self.project["id"])
            self.assertEqual(409, ctx.exception.status_code)
        preview = tasks.preview_task_changes(self.task["id"])
        self.assertEqual("unknown", preview["change_summary"]["state"])

    def test_preflight_failure_updates_original_run_and_redacts_exception(self):
        self.prepare_patch.stop()
        self.prepare_patch = patch.object(runner, "_prepare_run", side_effect=RuntimeError("TOPSECRET"))
        self.prepare_patch.start()
        run = self.trigger("bad-preflight")
        self.join_workers()
        failed = runner.get_run(run["id"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual("前置检查", failed["error_class"])
        self.assertNotIn("TOPSECRET", failed["error"])
        self.assertEqual(1, len(runner.list_runs()))

    def test_orphaned_queue_is_failed_once(self):
        db.execute("INSERT INTO task_runs(project_id,task_type,harness,prompt_version,queued_at)"
                   " VALUES (?,?,?,?,?)", (self.project["id"], "custom", "dummy", "", time.time() - 700))
        self.assertEqual(1, runner.sweep_stale_runs())
        self.assertEqual(0, runner.sweep_stale_runs())

    def test_cron_slot_runs_once_and_next_minute_can_run(self):
        self.gate.set()
        tasks.update_task(self.task["id"], {"schedule_cron": "* * * * *"})
        slot = int(time.time() // 60) * 60
        with patch.object(tasks.time, "time", return_value=slot + 5):
            tasks.scheduler_tick()
            self.join_workers()
            tasks.scheduler_tick()
            self.join_workers()
        self.assertEqual(1, len(runner.list_runs()))
        with patch.object(tasks.time, "time", return_value=slot + 65):
            tasks.scheduler_tick()
            self.join_workers()
        self.assertEqual(2, len(runner.list_runs()))

    def test_api_fast_accept_retry_and_conflict_codes(self):
        app = FastAPI()
        app.include_router(runs_router.router)
        app.include_router(tasks_router.router)
        admin = lambda: {"username": "admin", "role": "admin"}
        app.dependency_overrides[current_user] = admin
        app.dependency_overrides[require_admin] = admin
        with TestClient(app) as client:
            body = {"project_id": self.project["id"], "task_type": self.task["task_type"]}
            headers = {"Idempotency-Key": "api-click"}
            first = client.post("/api/runs/trigger", json=body, headers=headers)
            self.assertEqual(200, first.status_code)
            repeated = client.post("/api/runs/trigger", json=body, headers=headers)
            self.assertEqual(first.json()["id"], repeated.json()["id"])
            conflict = client.post(f"/api/tasks/{self.task['id']}/trigger")
            self.assertEqual(409, conflict.status_code)
            self.assertEqual(1, len(client.get("/api/runs").json()))

    def test_slow_preview_does_not_block_run_queries(self):
        preview_started, release_preview = threading.Event(), threading.Event()
        self.gates.append(release_preview)
        def preview(*args):
            preview_started.set()
            release_preview.wait(4)
            return {"change_summary": {"state": "initial"}}
        app = FastAPI()
        app.include_router(tasks_router.router)
        app.include_router(runs_router.router)
        for dependency in (current_user, require_admin):
            app.dependency_overrides[dependency] = lambda: {"username": "admin", "role": "admin"}
        with patch.object(tasks, "preview_task_changes", side_effect=preview), TestClient(app) as client:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                slow = pool.submit(client.get, f"/api/tasks/{self.task['id']}/changes")
                self.assertTrue(preview_started.wait(2))
                fast = pool.submit(client.get, "/api/runs")
                try:
                    self.assertEqual(200, fast.result(timeout=1).status_code)
                finally:
                    release_preview.set()
                self.assertEqual(200, slow.result(timeout=2).status_code)


if __name__ == "__main__":
    unittest.main()
