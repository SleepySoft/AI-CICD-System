import subprocess
import sys
import tempfile
import unittest
import json
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from chronicler.app import change_detection, db, projects, runner, tasks
from chronicler.app.config import Cfg


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args], check=True,
                               capture_output=True, encoding="utf-8", errors="replace")
    return completed.stdout.strip()


class ChangeDetectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        subprocess.run(["git", "init", "-b", "main", str(self.repo)], check=True,
                       capture_output=True)
        (self.repo / "file.txt").write_text("one\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "first")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def test_git_change_counts_commits_files_and_lines(self):
        (self.repo / "file.txt").write_text("one\ntwo\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "second")
        head = git(self.repo, "rev-parse", "HEAD")

        changed = change_detection._git_change(self.repo, self.base, head)
        unchanged = change_detection._git_change(self.repo, head, head)

        self.assertEqual("changed", changed["state"])
        self.assertEqual(1, changed["commits"])
        self.assertEqual(1, changed["files"])
        self.assertEqual(1, changed["insertions"])
        self.assertEqual("unchanged", unchanged["state"])

    def test_existing_project_sync_updates_to_new_upstream_commit(self):
        old_data, old_workspace = Cfg.DATA, Cfg.WORKSPACE
        old_connection = getattr(db._local, "conn", None)
        try:
            Cfg.WORKSPACE = Path(self.temp.name) / "workspace"
            db._local.conn = None
            Cfg.DATA = Path(self.temp.name) / "data-sync"
            db.init()
            project = projects.create_project("sync-sample", str(self.repo), default_branch="main")
            projects.sync_project(project["id"])
            old_head = projects.head_commit(project["id"])
            (self.repo / "file.txt").write_text("one\ntwo\n", encoding="utf-8")
            git(self.repo, "add", "-A")
            git(self.repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
                "commit", "-m", "upstream")

            projects.sync_project(project["id"])

            self.assertNotEqual(old_head, projects.head_commit(project["id"]))
            self.assertEqual(git(self.repo, "rev-parse", "HEAD"), projects.head_commit(project["id"]))
        finally:
            current = getattr(db._local, "conn", None)
            if current is not None:
                current.close()
            db._local.conn = old_connection
            Cfg.DATA = old_data
            Cfg.WORKSPACE = old_workspace

    def test_git_change_detects_diverged_history(self):
        git(self.repo, "checkout", "--orphan", "other")
        git(self.repo, "rm", "-rf", ".")
        (self.repo / "other.txt").write_text("other\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
            "commit", "-m", "other")
        head = git(self.repo, "rev-parse", "HEAD")

        result = change_detection._git_change(self.repo, self.base, head)

        self.assertEqual("diverged", result["state"])

    def test_command_probe_hashes_stdout_and_reports_failure(self):
        executable = f'"{sys.executable}"'
        ok = change_detection._run_probe(self.repo, {
            "name": "deps", "command": f'{executable} -c "print(123)"', "timeout_sec": 10})
        failed = change_detection._run_probe(self.repo, {
            "name": "broken", "command": f'{executable} -c "import sys;print(\'TOPSECRET\',file=sys.stderr);sys.exit(2)"',
            "timeout_sec": 10})

        self.assertEqual("ok", ok["status"])
        self.assertEqual(64, len(ok["fingerprint"]))
        self.assertNotIn("123", ok.values())
        self.assertEqual("unknown", failed["status"])
        self.assertNotIn("TOPSECRET", failed["error"])

    def test_capture_detects_probe_only_change_and_unknown(self):
        previous = {"primary": {"kind": "git", "revision": self.base},
                    "probes": [{"name": "deps", "status": "ok", "fingerprint": "old"}]}
        baseline = {"id": 9, "input_snapshot": {"source_snapshot": previous}}
        executable = f'"{sys.executable}"'
        with patch.object(change_detection, "_baseline", return_value=baseline), \
                patch.object(projects, "repo_dir", return_value=self.repo), \
                patch.object(projects, "head_commit", return_value=self.base):
            changed = change_detection.capture(1, "project-analysis", 2, [{
                "name": "deps", "command": f'{executable} -c "print(456)"'}])
            unknown = change_detection.capture(1, "project-analysis", 2, [{
                "name": "deps", "command": f'{executable} -c "import sys;sys.exit(2)"'}])

        self.assertEqual("changed", changed["change_summary"]["state"])
        self.assertEqual(["deps"], changed["change_summary"]["changed_probes"])
        self.assertEqual("unknown", unknown["change_summary"]["state"])
        self.assertTrue(unknown["change_summary"]["probe_errors"])

    def test_removing_a_probe_is_an_input_change(self):
        previous = {"primary": {"kind": "git", "revision": self.base},
                    "probes": [{"name": "deps", "status": "ok", "fingerprint": "old"}]}
        baseline = {"id": 9, "input_snapshot": {"source_snapshot": previous}}
        with patch.object(change_detection, "_baseline", return_value=baseline), \
                patch.object(projects, "repo_dir", return_value=self.repo), \
                patch.object(projects, "head_commit", return_value=self.base):
            result = change_detection.capture(1, "project-analysis", 2, [])

        self.assertEqual("changed", result["change_summary"]["state"])
        self.assertEqual(["deps（已移除）"], result["change_summary"]["changed_probes"])

    def test_policies_skip_only_known_unchanged_inputs(self):
        unchanged = {"state": "unchanged", "repo_state": "unchanged"}
        probe_changed = {"state": "changed", "repo_state": "unchanged"}
        unknown = {"state": "unknown", "repo_state": "unknown"}
        probe_unknown = {"state": "unknown", "repo_state": "unchanged"}

        self.assertFalse(change_detection.should_skip("always", unchanged))
        self.assertTrue(change_detection.should_skip("repo-changed", probe_changed))
        self.assertFalse(change_detection.should_skip("inputs-changed", probe_changed))
        self.assertTrue(change_detection.should_skip("inputs-changed", unchanged))
        self.assertFalse(change_detection.should_skip("repo-changed", unknown))
        self.assertFalse(change_detection.should_skip("repo-changed", probe_unknown))
        with self.assertRaises(HTTPException):
            change_detection.should_skip("invalid", unchanged)

    def test_cron_trigger_with_unchanged_repo_creates_skipped_run(self):
        old_paths = Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE
        old_connection = getattr(db._local, "conn", None)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            shadow_remote = root / "shadow.git"
            subprocess.run(["git", "init", "-b", "main", str(source)], check=True,
                           capture_output=True)
            subprocess.run(["git", "init", "--bare", str(shadow_remote)], check=True,
                           capture_output=True)
            (source / "README.md").write_text("source\n", encoding="utf-8")
            git(source, "add", "-A")
            git(source, "-c", "user.name=test", "-c", "user.email=test@example.com",
                "commit", "-m", "source")
            try:
                Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE = root / "data", root / "public", root / "workspace"
                db._local.conn = None
                db.init()
                project = projects.create_project("sample", str(source), default_branch="main",
                                                  shadow_repo=str(shadow_remote))
                task = tasks.create_task(project["id"], "analysis", "project-analysis",
                                         change_policy="repo-changed")
                projects.sync_project(project["id"])
                revision = projects.head_commit(project["id"])
                baseline_snapshot = {"repo_head": revision, "source_snapshot": {
                    "primary": {"kind": "git", "revision": revision}, "probes": []}}
                baseline_id = db.execute(
                    "INSERT INTO task_runs(task_id, project_id, task_type, status, trigger, harness,"
                    " prompt_version, input_snapshot, created_by, started_at, finished_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (task["id"], project["id"], task["task_type"], "success", "manual", "dummy",
                     "test", json.dumps(baseline_snapshot), "test", time.time(), time.time()))

                run = runner.trigger(project["id"], task["task_type"], "cron",
                                     task_id=task["id"], change_policy="repo-changed",
                                     change_probes=[], allow_skip=True, trigger_kind="cron")

                self.assertEqual("skipped", run["status"])
                self.assertEqual("cron", run["trigger"])
                self.assertEqual(baseline_id, run["input_snapshot"]["baseline_run_id"])
                self.assertEqual("unchanged", run["input_snapshot"]["change_summary"]["state"])
                self.assertIn("无增量", run["error_class"])
                failed = runner.record_preflight_failure(task, "cron", RuntimeError("TOPSECRET"))
                self.assertEqual("failed", failed["status"])
                self.assertNotIn("TOPSECRET", failed["error"])
                audit_detail = db.q("SELECT detail FROM audit_log ORDER BY id DESC LIMIT 1")[0]["detail"]
                self.assertNotIn("TOPSECRET", audit_detail)
                tasks.delete_task(task["id"])
                preserved = db.q("SELECT task_id FROM task_runs WHERE project_id=?", (project["id"],))
                self.assertTrue(preserved)
                self.assertTrue(all(item["task_id"] is None for item in preserved))
            finally:
                current = getattr(db._local, "conn", None)
                if current is not None:
                    current.close()
                db._local.conn = old_connection
                Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE = old_paths


if __name__ == "__main__":
    unittest.main()