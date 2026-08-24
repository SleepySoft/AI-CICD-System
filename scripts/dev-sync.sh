#!/usr/bin/env bash
# 开发辅助：统一 LF + 补齐 .env 新变量
set -euo pipefail
cd "$(dirname "$0")/.."
grep -rlP '\r$' --exclude='*.ps1' manager images scripts keycloak caddy docker-compose.yml .env.example 2>/dev/null | xargs -r sed -i 's/\r$//' || true
[ -f .env ] || cp .env.example .env
for v in \
  "OIDC_MANAGER_SECRET=manager-oidc-secret-change-me" \
  "MANAGER_SESSION_SECRET=manager_session_secret_change_me_0123456789" \
  "ATR_API_TOKEN=atr_token_change_me"; do
  grep -q "^${v%%=*}=" .env || echo "$v" >> .env
done
echo "ok, .env 变量数: $(grep -c . .env)"
