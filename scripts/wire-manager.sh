#!/usr/bin/env bash
# 为 Manager 在运行中的 Keycloak 创建 OIDC 客户端（幂等，使用 kcadm）
# 用法: ./scripts/wire-manager.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

KC=/opt/keycloak/bin/kcadm.sh
C=aisystem-keycloak-1

echo "==> kcadm 登录"
docker exec "$C" \
  $KC config credentials --server http://localhost:8080 --realm master \
  --user "${KEYCLOAK_ADMIN:-admin}" --password "${KEYCLOAK_ADMIN_PASSWORD:?}" >/dev/null

echo "==> 检查 manager 客户端是否已存在"
EXISTING=$(docker exec "$C" $KC get clients -r aisystem --query clientId=manager --fields id --format csv --noquotes 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "   已存在（id=$EXISTING），跳过创建"
else
  docker exec -i -e KC_SECRET="${OIDC_MANAGER_SECRET:?}" "$C" \
    $KC create clients -r aisystem -f - <<EOF
{
  "clientId": "manager",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "secret": "${OIDC_MANAGER_SECRET:?}",
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "redirectUris": ["http://app.localhost/api/auth/callback", "http://app.localhost/*"],
  "webOrigins": ["http://app.localhost"],
  "defaultClientScopes": ["web-origins", "acr", "profile", "email", "roles", "groups"]
}
EOF
  echo "   已创建"
fi
echo "==> 完成"
