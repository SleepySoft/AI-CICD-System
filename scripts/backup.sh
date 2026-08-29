#!/usr/bin/env bash
# 一键备份（薄壳）：委托 Chronicler 组件化编排器（ADR-0027）
# 组件钩子自负其责；本脚本只负责找到 python 并调用
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x chronicler/.venv/bin/python ] && PY=chronicler/.venv/bin/python
[ -x chronicler/.venv-win/Scripts/python.exe ] && PY=chronicler/.venv-win/Scripts/python.exe

"$PY" -m chronicler backup "$@"
echo "恢复: $PY -m chronicler restore <备份目录>（详见 docs/runbooks/backup-restore.md）"
