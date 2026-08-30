#!/usr/bin/env bash
# 一键启动（幂等）：共享网络 → supervisor（自启钩子拉起全部自启组件）→ SSO 接线 → 验证
# 注：组件部署定义在各组件目录（components/<name>/compose.yml），根 compose 已废除（ADR-0027）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "==> .env 不存在，从模板创建（请修改其中的 *_change_me）"
    cp .env.example .env
fi

echo "==> 共享网络"
docker network inspect aisystem >/dev/null 2>&1 || docker network create aisystem

echo "==> 启动 supervisor（其自启钩子会拉起标记自启的组件）"
if [ -f scripts/start-chronicler.ps1 ] && command -v powershell >/dev/null 2>&1; then
    powershell -ExecutionPolicy Bypass -File scripts/start-chronicler.ps1 &
elif [ -x chronicler/.venv/bin/python ]; then
    nohup chronicler/.venv/bin/python -m chronicler serve > /tmp/chronicler.log 2>&1 &
else
    echo "请先安装 chronicler 依赖（见 docs/runbooks/deploy.md）"; exit 1
fi
sleep 8

echo "==> 等待核心组件（autostart 钩子拉起中）"
for i in $(seq 1 24); do
  ok=$(docker ps --filter name=aisystem-keycloak-1 --format '{{.Status}}' 2>/dev/null | grep -c healthy || true)
  [ "$ok" = "1" ] && break
  sleep 5
done

echo "==> SSO 接线（幂等）"
bash scripts/wire-sso.sh

echo "==> 冒烟验证"
bash scripts/verify.sh || true
bash scripts/verify-chronicler.sh || true

echo
echo "==> 完成。入口：http://app.localhost（Chronicler，首页=统一门户）"
