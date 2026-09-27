import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import db, projects, registry, runner
from chronicler.app.config import Cfg
from chronicler.app.routers import runs
from chronicler.app.runtime import RuntimeProfile


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class RuntimeProfileTest(unittest.TestCase):
    def test_sealed_run_persists_metadata_and_removes_temporary_prompt(self):
        old_paths = Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE
        old_connection = getattr(db._local, "conn", None)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            shadow = root / "shadow.git"
            subprocess.run(["git", "init", "-b", "main", str(source)], check=True,
                           capture_output=True)
            subprocess.run(["git", "init", "--bare", str(shadow)], check=True,
                           capture_output=True)
            (source / "README.md").write_text("source\n", encoding="utf-8")
            git(source, "add", "-A")
            git(source, "-c", "user.name=test", "-c", "user.email=test@example.com",
                "commit", "-m", "source")
            sealed = RuntimeProfile("sealed", root, root / "resources", root / "components",
                                    "metadata-only", False, b"x" * 32)
            try:
                Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE = root / "data", root / "public", root / "workspace"
                db._local.conn = None
                with patch.object(db, "PROFILE", sealed):
                    db.init()
                project = projects.create_project("sealed", str(source), default_branch="main",
                                                  shadow_repo=str(shadow))
                with patch.object(runner, "PROFILE", sealed), \
                    patch.object(runner, "_run"):
                    run = runner.trigger(project["id"], "operational_reporter", "test",
                                         harness_override="dummy")
                    with runner._workers_guard:
                        worker = runner._workers.get(run["id"])
                    if worker:
                        worker.join(10)
                        self.assertFalse(worker.is_alive())
                    run = runner.get_run(run["id"])
                stored = db.q1("SELECT prompt_text FROM task_runs WHERE id=?", (run["id"],))
                snapshot = run["input_snapshot"]
                self.assertEqual("", stored["prompt_text"])
                self.assertEqual("operational_reporter", snapshot["prompt_name"])
                self.assertEqual("1.2.0", snapshot["prompt_version"])
                self.assertTrue(snapshot["prompt_hash"].startswith("sha256:"))

                harness = registry.get_harness("dummy")
                def execute_started(*args):
                    active = runner.get_run(run["id"])
                    self.assertEqual(active["status"], "running")
                    self.assertIsNotNone(active["started_at"])
                    self.assertGreaterEqual(active["started_at"], active["queued_at"])
                    return 1, ""
                with patch.object(runner, "PROFILE", sealed), \
                        patch.object(runner, "_exec", side_effect=execute_started):
                    runner._run(run["id"], harness, "TOPSECRET")
                self.assertFalse((Cfg.runs_dir() / str(run["id"]) / "prompt.md").exists())

                with patch.object(runs, "PROFILE", sealed):
                    prompt_info = asyncio.run(runs.prompt(run["id"], {"username": "test"}))
                self.assertIn("name: operational_reporter", prompt_info)
                self.assertIn("version: 1.2.0", prompt_info)
                self.assertNotIn("TOPSECRET", prompt_info)
            finally:
                current = getattr(db._local, "conn", None)
                if current is not None:
                    current.close()
                db._local.conn = old_connection
                Cfg.DATA, Cfg.PUBLIC, Cfg.WORKSPACE = old_paths


if __name__ == "__main__":
    unittest.main()
