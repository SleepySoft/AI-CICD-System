#!/usr/bin/env bash
# Manager + ATR 冒烟验证
set -u
H="Host: app.localhost"

echo '--- manager 页面/健康 ---'
curl --noproxy '*' -s -o /dev/null -w 'app /            -> %{http_code}\n' -H "$H" http://127.0.0.1/
curl --noproxy '*' -s -H "$H" http://127.0.0.1/api/health; echo

echo '--- 未登录访问受保护 API（应 401） ---'
curl --noproxy '*' -s -o /dev/null -w 'app /api/tools         -> %{http_code}\n' -H "$H" http://127.0.0.1/api/tools
curl --noproxy '*' -s -o /dev/null -w 'app /api/agent/sessions -> %{http_code}\n' -H "$H" http://127.0.0.1/api/agent/sessions

echo '--- 登录跳转（应 302 到 keycloak） ---'
curl --noproxy '*' -s -o /dev/null -w 'app /api/auth/login -> %{http_code} redirect=%{redirect_url}\n' -H "$H" http://127.0.0.1/api/auth/login

echo '--- ATR 直连（容器内，带 token） ---'
TOKEN=$(grep ^ATR_API_TOKEN .env | cut -d= -f2)
docker exec -e TOKEN="$TOKEN" aisystem-terminal-runtime-1 bash -c \
  'curl -s -H "Authorization: Bearer $TOKEN" http://localhost:18650/health'
echo

echo '--- ATR 端到端：创建 bash 会话 → 提交命令 → 截图 → 删除 ---'
docker exec -e TOKEN="$TOKEN" aisystem-terminal-runtime-1 bash -c '
set -e
B=http://localhost:18650
AUTH="Authorization: Bearer $TOKEN"
curl -s -X POST $B/sessions -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"id\":\"smoke-1\",\"command\":\"bash\",\"rows\":20,\"cols\":80}" > /dev/null
sleep 2
curl -s -X POST $B/sessions/smoke-1/actions -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"actor\":\"smoke\",\"action\":{\"type\":\"submit\",\"text\":\"echo ATR-WORKS-$(date +%s)\"}}" > /dev/null
sleep 1
curl -s $B/sessions/smoke-1/screenshot -H "$AUTH" | grep -o "ATR-WORKS-[0-9]*" | head -n 1
curl -s -X DELETE $B/sessions/smoke-1 -H "$AUTH" > /dev/null
echo ATR-E2E-DONE
'
