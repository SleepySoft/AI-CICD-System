import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chronicler.app import projects, registry, runner


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          encoding="utf-8", errors="replace")


class PublicationPolicyTest(unittest.TestCase):
    def test_direct_is_the_default_and_only_implemented_policy(self):
        with patch.object(registry, "load_settings", return_value={}):
            self.assertEqual("direct", registry.get_publish_policy())
            self.assertEqual(("direct",), registry.PUBLISH_POLICIES)

    def test_direct_commits_and_pushes_only_main(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / "work"
            remote = root / "remote.git"
            git("init", "-b", "master", str(work))
            git("init", "--bare", str(remote))
            (work / "README.md").write_text("initial\n", encoding="utf-8")
            git("-C", str(work), "add", "-A")
            git("-C", str(work), "-c", "user.name=test", "-c",
                "user.email=test@example.com", "commit", "-m", "initial")

            project = {"id": 1, "shadow_repo": str(remote)}
            with patch.object(projects, "ensure_shadow_repo", return_value=work), \
                    patch.object(projects, "shadow_dir", return_value=work), \
                    patch.object(projects, "get_project", return_value=project):
                projects.prepare_shadow_direct(1)
                (work / "docs.md").write_text("generated\n", encoding="utf-8")
                sha, artifacts, publication = runner._commit_shadow(
                    {"id": 42, "project_id": 1, "task_type": "structured-docs",
                     "input_snapshot": {"shadow_base_commit": "base"}},
                    "direct")

            self.assertTrue(sha)
            self.assertTrue(artifacts)
            self.assertEqual("pushed", publication["push_status"])
            self.assertEqual(["main"], git("-C", str(work), "branch",
                                           "--format=%(refname:short)").stdout.split())
            self.assertEqual(["main"], git("--git-dir", str(remote), "branch",
                                           "--format=%(refname:short)").stdout.split())


if __name__ == "__main__":
    unittest.main()