#!/usr/bin/env bash
# 一键底座（幂等）：校验 .env 与 supervisor 前置 → 共享网络 → 等核心组件（supervisor autostart 钩子拉起）→ SSO 接线 → 验证
# 注：组件部署定义在各组件目录（components/<name>/compose.yml），根 compose 已废除（ADR-0027）；
#     supervisor 唯一启动入口是主入口 `python -m chronicler serve`（缺 .env 会提示并退出），本脚本不再拉起它。
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "==> [ERROR] 缺少首要依赖 .env，请先创建并配置："
    echo "    cp .env.example .env          # WSL/Linux"
    echo "    Copy-Item .env.example .env   # Windows PowerShell"
    echo "    并编辑其中所有 *_change_me（保持非空即可）。"
    exit 1
fi

echo "==> 检查 supervisor（主入口 python -m chronicler serve 须已运行）"
if ! curl --noproxy '*' -fsS -o /dev/null http://127.0.0.1:8600/api/health; then
    echo "==> [ERROR] supervisor 未运行（http://127.0.0.1:8600 无响应）。请先用主入口启动："
    echo "    chronicler/.venv/bin/python -m chronicler serve                    # WSL/Linux"
    echo "    chronicler\\.venv-win\\Scripts\\python.exe -m chronicler serve      # Windows"
    exit 1
fi

echo "==> 共享网络"
docker network inspect aisystem >/dev/null 2>&1 || docker network create aisystem

echo "==> 等待核心组件（supervisor autostart 钩子拉起中）"
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
