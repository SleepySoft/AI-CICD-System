#!/usr/bin/env python3
"""postgres 组件备份钩子（ADR-0027 契约）
用法: backup.py backup --dest <dir> | restore --src <dir> | manifest
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CONTAINER = "aisystem-postgres-1"
USER = os.environ.get("POSTGRES_USER", "aisys")


def _container_running() -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def manifest():
    print(json.dumps({"covers": ["postgres 全库（pg_dumpall）"], "requires": []}))


def backup(dest: Path):
    if not _container_running():
        print(json.dumps({"skipped": True, "reason": "容器未运行"}))
        return
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "pg_dumpall.sql"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        r = subprocess.run(["docker", "exec", CONTAINER, "pg_dumpall", "-U", USER],
                           stdout=f, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(json.dumps({"error": r.stderr[-300:]}))
        sys.exit(1)
    print(json.dumps({"covers": ["postgres 全库"], "files": [out.name],
                      "size_bytes": out.stat().st_size}))


def restore(src: Path):
    dump = src / "pg_dumpall.sql"
    if not dump.is_file():
        print(json.dumps({"skipped": True, "reason": "无 pg_dumpall.sql"}))
        return
    if not _container_running():
        print(json.dumps({"error": "容器未运行，无法恢复"}))
        sys.exit(1)
    with open(dump, encoding="utf-8") as f:
        r = subprocess.run(["docker", "exec", "-i", CONTAINER, "psql", "-U", USER],
                           stdin=f, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(json.dumps({"error": r.stderr[-300:]}))
        sys.exit(1)
    print(json.dumps({"restored": ["postgres 全库"]}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "manifest"
    if cmd == "manifest":
        manifest()
    elif cmd == "backup":
        backup(Path(sys.argv[sys.argv.index("--dest") + 1]))
    elif cmd == "restore":
        restore(Path(sys.argv[sys.argv.index("--src") + 1]))
    else:
        sys.exit(__doc__)
