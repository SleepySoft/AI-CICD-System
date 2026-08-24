#!/usr/bin/env bash
# 冒烟验证：核心栈各入口 HTTP 状态
# 注：WSL 内不解析 *.localhost，先用 Host 头方式验证；
#     可选：执行 sudo ./scripts/fix-hosts.sh 写入 /etc/hosts 后即可用域名访问
set -u
hosts="portal git ci sso kb docs req vectors status browser llm"
for u in $hosts; do
  code=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' -H "Host: $u.localhost" http://127.0.0.1/ || true)
  echo "$u.localhost -> HTTP $code"
done
echo '--- keycloak realm ---'
curl --noproxy '*' -s -H "Host: sso.localhost" http://127.0.0.1/realms/aisystem/.well-known/openid-configuration | head -c 120; echo
echo '--- gitea api ---'
curl --noproxy '*' -s -H "Host: git.localhost" http://127.0.0.1/api/v1/version; echo
