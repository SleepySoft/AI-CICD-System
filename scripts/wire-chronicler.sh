#!/usr/bin/env bash
# 为 Chronicler 在运行中的 Keycloak 创建 OIDC 客户端（幂等，使用 kcadm）
# 前置：.env 中设置 CHRONICLER_OIDC_SECRET；用法: bash scripts/wire-chronicler.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

KC=/opt/keycloak/bin/kcadm.sh
C=aisystem-keycloak-1

echo "==> kcadm 登录"
docker exec "$C" \
  $KC config credentials --server http://localhost:8080 --realm master \
  --user "${KEYCLOAK_ADMIN:-admin}" --password "${KEYCLOAK_ADMIN_PASSWORD:?}" >/dev/null

# ---- realm 内建 scope 缺失修复（本 realm 模板仅含 groups；profile/email 需手动建） ----
scope_id() {
  docker exec "$C" $KC get client-scopes -r aisystem --fields id,name --format csv --noquotes \
    | tr -d '\r' | awk -F, -v n="$1" '$2==n {print $1}'
}
create_scope() {
  [ -n "$(scope_id "$1")" ] && return 0
  printf '{"name":"%s","protocol":"openid-connect","attributes":{"include.in.token.scope":"true","display.on.consent.screen":"false"}}' "$1" \
    | docker exec -i "$C" $KC create client-scopes -r aisystem -f - >/dev/null
}
add_mapper() {
  local SID JSON
  SID=$(scope_id "$1")
  JSON=$(printf '{"name":"%s","protocol":"openid-connect","protocolMapper":"oidc-usermodel-property-mapper","config":{"user.attribute":"%s","claim.name":"%s","jsonType.label":"String","id.token.claim":"true","access.token.claim":"true","userinfo.token.claim":"true"}}' "$2" "$3" "$2")
  echo "$JSON" | docker exec -i "$C" $KC create "client-scopes/$SID/protocol-mappers/models" -r aisystem -f - >/dev/null 2>&1 || true
}
assign_scope() {  # $1=client $2=scope
  local CID SID
  CID=$(docker exec "$C" $KC get clients -r aisystem --fields id,clientId --format csv --noquotes \
        | tr -d '\r' | awk -F, -v n="$1" '$2==n {print $1}')
  SID=$(scope_id "$2")
  [ -n "$CID" ] && [ -n "$SID" ] && \
    docker exec "$C" $KC update "clients/$CID/default-client-scopes/$SID" -r aisystem -n >/dev/null 2>&1 || true
}

echo "==> 确保 profile/email scope 存在并分配（幂等）"
create_scope profile
add_mapper profile preferred_username username
create_scope email
add_mapper email email email
for cli in chronicler gitea outline; do
  assign_scope "$cli" profile
  assign_scope "$cli" email
done

echo "==> 检查 chronicler 客户端是否已存在"
EXISTING=$(docker exec "$C" $KC get clients -r aisystem --query clientId=chronicler --fields id --format csv --noquotes 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "   已存在（id=$EXISTING），跳过创建"
else
  docker exec -i -e KC_SECRET="${CHRONICLER_OIDC_SECRET:?请在 .env 设置 CHRONICLER_OIDC_SECRET}" "$C" \
    $KC create clients -r aisystem -f - <<EOF
{
  "clientId": "chronicler",
  "enabled": true,
  "protocol": "openid-connect",
  "publicClient": false,
  "secret": "${CHRONICLER_OIDC_SECRET:?}",
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "redirectUris": ["http://app.localhost/api/auth/oidc/callback", "http://app.localhost/*"],
  "webOrigins": ["http://app.localhost"],
  "defaultClientScopes": ["web-origins", "acr", "profile", "email", "roles", "groups"]
}
EOF
  echo "   已创建"
fi
echo "==> 完成。supervisor 侧设 CHRONICLER_AUTH_BACKEND=oidc 后重启生效"
