#!/usr/bin/env bash
# 恢复（薄壳）：委托 Chronicler 组件化编排器（ADR-0027）
# 用法: bash scripts/restore.sh data/backups/<时间戳>
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
[ -x chronicler/.venv/bin/python ] && PY=chronicler/.venv/bin/python
[ -x chronicler/.venv-win/Scripts/python.exe ] && PY=chronicler/.venv-win/Scripts/python.exe

[ $# -ge 1 ] || { echo "用法: $0 <备份目录>"; exit 1; }
echo "警告：恢复将覆盖现有数据（详见 docs/runbooks/backup-restore.md）"
read -r -p "确认恢复 $1 ? [y/N] " ans
[ "$ans" = "y" ] || exit 0
"$PY" -m chronicler restore "$1"
