import subprocess
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import db, tasks
from chronicler.app.config import Cfg
from chronicler.app import projects


def isolated_db(root: Path):
    """隔离数据目录并初始化测试数据库。"""
    patches = [
        patch.object(Cfg, "DATA", root / "private" / "chronicler"),
        patch.object(Cfg, "PUBLIC", root / "public"),
        patch.object(Cfg, "WORKSPACE", root / "workspace"),
    ]
    for item in patches:
        item.start()
    db.close()
    db.init()
    return patches


class ProjectCreationBootstrapTest(unittest.TestCase):
    def test_create_project_adds_two_formal_tasks_and_seedable_shadow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patches = isolated_db(root)
            try:
                from chronicler.app.routers import projects as projects_router
                project = asyncio.run(projects_router.create(projects_router.ProjectBody(
                    name="bootstrap",
                    git_url="https://example.invalid/source.git",
                    default_branch="main",
                ), {"id": 1, "username": "admin", "role": "admin"}))
                created = tasks.list_tasks(project["id"])
                self.assertEqual(tasks.PRESET_TASKS,
                                 [item["task_type"] for item in created])
                self.assertTrue(all(item["enabled"] for item in created))

                with patch.object(projects, "_auto_shadow_repo", return_value=None):
                    shadow = projects.ensure_shadow_repo(project["id"])
                self.assertTrue((shadow / "SKILL.md").is_file())
                self.assertTrue((shadow / "README.md").is_file())
                self.assertTrue((shadow / ".cognitive-state.yaml").is_file())
                self.assertTrue((shadow / "templates" / "requirement.md").is_file())
                state = (shadow / ".cognitive-state.yaml").read_text(encoding="utf-8")
                self.assertIn('repository: "bootstrap"', state)
            finally:
                db.close()
                for item in reversed(patches):
                    item.stop()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          encoding="utf-8", errors="replace")


class ShadowTemplateTest(unittest.TestCase):
    def test_new_local_shadow_repo_is_initialized_from_template(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "sample-shadow"
            project = {"id": 1, "name": "sample", "git_url": "https://example.invalid/source.git",
                       "default_branch": "main", "shadow_repo": ""}
            with patch.object(projects, "get_project", return_value=project), \
                    patch.object(projects, "shadow_dir", return_value=dest), \
                    patch.object(projects, "_auto_shadow_repo", return_value=None):
                result = projects.ensure_shadow_repo(1)

            self.assertEqual(dest, result)
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertTrue((dest / "README.md").is_file())
            self.assertTrue((dest / ".cognitive-state.yaml").is_file())
            for name in ("cognitive-state.yaml", "requirement.md", "adr.md", "know-how.md",
                         "assessment.md", "run-record.md"):
                self.assertTrue((dest / "templates" / name).is_file())
            self.assertEqual("main", git("-C", str(dest), "branch",
                                         "--show-current").stdout.strip())
            self.assertEqual("init cognitive shadow", git(
                "-C", str(dest), "log", "-1", "--format=%s").stdout.strip())
            state = (dest / ".cognitive-state.yaml").read_text(encoding="utf-8")
            self.assertIn('repository: "sample"', state)
            self.assertIn('branch: "main"', state)
            self.assertIn("commit: \"\"", state)

    def test_existing_remote_shadow_repo_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "shadow.git"
            work = root / "work"
            git("init", "-b", "main", "--bare", str(remote))
            git("clone", str(remote), str(work))
            (work / "README.md").write_text("existing\n", encoding="utf-8")
            git("-C", str(work), "add", "-A")
            git("-C", str(work), "-c", "user.name=test", "-c",
                "user.email=test@example.com", "commit", "-m", "existing")
            git("-C", str(work), "push", "origin", "main")
            dest = root / "cloned-shadow"
            project = {"id": 1, "name": "sample", "git_url": "https://example.invalid/source.git",
                       "default_branch": "main", "shadow_repo": str(remote)}
            with patch.object(projects, "get_project", return_value=project), \
                    patch.object(projects, "shadow_dir", return_value=dest):
                projects.ensure_shadow_repo(1)

            self.assertTrue((dest / "README.md").is_file())
            self.assertFalse((dest / "SKILL.md").exists())
            self.assertFalse((dest / ".cognitive-state.yaml").exists())

    def test_empty_remote_shadow_repo_is_initialized_from_template(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "shadow.git"
            git("init", "-b", "main", "--bare", str(remote))
            dest = root / "cloned-shadow"
            project = {"id": 1, "name": "sample", "git_url": "https://example.invalid/source.git",
                       "default_branch": "main", "shadow_repo": str(remote)}
            with patch.object(projects, "get_project", return_value=project), \
                    patch.object(projects, "shadow_dir", return_value=dest):
                projects.ensure_shadow_repo(1)

            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertEqual("main", git("-C", str(dest), "branch",
                                         "--show-current").stdout.strip())
            self.assertEqual("init cognitive shadow", git(
                "-C", str(dest), "log", "-1", "--format=%s").stdout.strip())


if __name__ == "__main__":
    unittest.main()
