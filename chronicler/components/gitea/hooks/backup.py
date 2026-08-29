#!/usr/bin/env python3
"""gitea 组件备份钩子（ADR-0027 契约）：数据目录打包（DB 在 postgres，由其钩子覆盖）
用法: backup.py backup --dest <dir> | restore --src <dir> | manifest
"""
import json
import subprocess
import sys
import tarfile
from pathlib import Path

CONTAINER = "aisystem-gitea-1"
# ADR-0026 迁移前为 data/gitea，迁移后 data/private/gitea——两者都探测
DATA_CANDIDATES = [Path("data/private/gitea"), Path("data/gitea")]


def _data_dir() -> Path | None:
    for p in DATA_CANDIDATES:
        if p.is_dir():
            return p
    return None


def manifest():
    print(json.dumps({"covers": ["gitea 数据目录（仓库/附件/配置）"],
                      "requires": ["postgres"]}))  # gitea 元数据在 postgres，恢复须先 postgres


def backup(dest: Path):
    src = _data_dir()
    if not src:
        print(json.dumps({"skipped": True, "reason": "数据目录不存在"}))
        return
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "gitea-data.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(src, arcname="gitea")
    print(json.dumps({"covers": [str(src)], "files": [out.name],
                      "size_bytes": out.stat().st_size}))


def restore(src: Path):
    pkg = src / "gitea-data.tar.gz"
    if not pkg.is_file():
        print(json.dumps({"skipped": True, "reason": "无 gitea-data.tar.gz"}))
        return
    target = Path("data/gitea")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(pkg) as tar:
        tar.extractall(target.parent, filter="data")
    print(json.dumps({"restored": [str(target)]}))


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
