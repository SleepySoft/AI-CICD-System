#!/usr/bin/env bash
# 一键启动：起核心栈 → SSO 接线 → 冒烟验证
# 用法: bash scripts/up.sh            # 日常启动（幂等，可反复执行）
# 首次部署前请确认 .env 已就绪（cp .env.example .env 并修改 *_change_me）
# 注：supervisor（Chronicler）是宿主侧进程（ADR-0020），不在本脚本拉起；
#     启动方式见 docs/runbooks/deploy.md（python -m chronicler serve 或 systemd）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "==> .env 不存在，从模板创建（请稍后修改其中的 *_change_me）"
    cp .env.example .env
fi

echo "==> docker compose up -d（核心栈）"
docker compose up -d

echo "==> SSO 接线（幂等）"
bash scripts/wire-sso.sh

echo "==> 冒烟验证"
bash scripts/verify.sh
bash scripts/verify-chronicler.sh

echo
echo "==> 完成。入口：http://portal.localhost（门户）/ http://app.localhost（Chronicler）"
echo "    可选 profile 按需启动，如: docker compose --profile knowledge up -d"
echo "    ATR 沙箱：docker compose --profile sandbox up -d"
