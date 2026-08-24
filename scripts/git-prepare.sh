#!/usr/bin/env bash
# 一次性：移除 vendored 仓库的内嵌 .git，add + 提交
set -euo pipefail
cd /mnt/c/D/code/AI-CICD-System
rm -rf third_party/terminal-runtime-skill/.git
git add -A
git add --renormalize . 2>/dev/null || true
git status --short | head -n 20
echo "---- 文件总数 ----"
git diff --cached --name-only | wc -l
