import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import projects


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
