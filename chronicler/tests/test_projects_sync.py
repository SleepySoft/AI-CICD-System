"""工程同步安全守卫：损坏克隆不得让 git 逃逸到宿主仓库（2026-09-05 实测事故）。

事故形态：data/workspace/repos/<id> 的 .git 残缺/丢失后，sync_project 的
`git -C <dest> reset --hard origin/<branch>` 向上逃逸到宿主源码库执行，
主仓库未推送提交被抹掉。守卫：dest 必须是 toplevel==自身的独立 git 仓库。
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from chronicler.app import db, projects
from chronicler.app.config import Cfg


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          encoding="utf-8", errors="replace")


class SyncGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # 宿主仓库（嵌套逃逸的外层目标）
        _git(self.root, "init", "-b", "main")
        (self.root / "f.txt").write_text("v1", encoding="utf-8")
        _git(self.root, "add", ".")
        _git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
        self.patches = (patch.object(Cfg, "DATA", self.root / "private" / "chronicler"),
                        patch.object(Cfg, "WORKSPACE", self.root / "workspace"))
        for p in self.patches:
            p.start()
        db.close()
        db.init()
        db.execute("INSERT INTO projects(id, name, git_url, created_at) VALUES (1,'demo','',1)")

    def tearDown(self):
        db.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_broken_clone_never_escapes_to_host_repo(self):
        dest = projects.repo_dir(1)
        dest.mkdir(parents=True)  # 目录存在但不是独立 git 仓库（.git 残缺/丢失形态）
        head_before = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        with self.assertRaises(HTTPException) as ctx:
            projects.sync_project(1)
        assert ctx.exception.status_code == 409
        # 宿主仓库未被做任何 git 写操作（HEAD 不变；除我们刚建的 workspace 目录外无变化）
        assert _git(self.root, "rev-parse", "HEAD").stdout.strip() == head_before
        changes = [ln for ln in _git(self.root, "status", "--porcelain").stdout.splitlines()
                   if "workspace/" not in ln and "private/" not in ln]
        assert changes == [], changes
        assert "损坏" in projects.get_project(1)["last_sync_error"]

    def test_standalone_repo_passes_guard(self):
        dest = projects.repo_dir(1)
        dest.mkdir(parents=True)
        _git(dest, "init", "-b", "main")
        assert projects._is_own_repo(dest)
        assert not projects._is_own_repo(self.root / "workspace")  # 会逃逸到外层 → False


if __name__ == "__main__":
    unittest.main()
