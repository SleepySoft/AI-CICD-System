#!/usr/bin/env bash
# Gitea 接入 Keycloak OIDC（一次性接线）
# 前置: core 栈已启动且 keycloak/gitea 健康；.env 中 OIDC_GITEA_SECRET 与 realm 一致
# 用法: ./scripts/wire-sso.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

# 等待 keycloak / gitea 就绪（WSL 空闲重启后服务需要时间恢复）
echo "==> 等待 keycloak 就绪"
for i in $(seq 1 40); do
  if docker exec aisystem-keycloak-1 bash -c "exec 3<>/dev/tcp/localhost/8080 && echo -e 'GET /realms/aisystem/.well-known/openid-configuration HTTP/1.0\r\n\r\n' >&3 && grep -q '200' <&3" 2>/dev/null; then
    break
  fi
  sleep 5
done
echo "==> 等待 gitea 就绪"
for i in $(seq 1 24); do
  if docker exec -u git aisystem-gitea-1 wget -qO- http://localhost:3000/api/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo "==> 注册 Gitea OIDC 认证源 (keycloak)"
docker exec -u git aisystem-gitea-1 gitea admin auth add-oauth \
  --name keycloak \
  --provider openidConnect \
  --key gitea \
  --secret "${OIDC_GITEA_SECRET:-gitea-oidc-secret-change-me}" \
  --auto-discover-url "http://keycloak:8080/realms/aisystem/.well-known/openid-configuration" \
  --group-claim-name groups \
  --admin-group boss \
  || echo "   (可能已存在，忽略)"

echo "==> 创建 Gitea 管理员（若不存在）"
docker exec -u git aisystem-gitea-1 gitea admin user create \
  --admin \
  --username "${GITEA_ADMIN_USER:-gitea_admin}" \
  --password "${GITEA_ADMIN_PASSWORD:?GITEA_ADMIN_PASSWORD required}" \
  --email "${GITEA_ADMIN_USER:-gitea_admin}@aisystem.local" \
  --must-change-password=false \
  || echo "   (可能已存在，忽略)"

echo "==> 完成。Gitea 登录页将出现 'Sign in with keycloak'，boss 组自动获得管理员权限"
