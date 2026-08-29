#!/usr/bin/env bash
# 手动触发 webhook 测试投递，并检查 gitea 侧投递记录
set -uo pipefail
cd "$(dirname "$0")/.."
PASS=$(grep ^GITEA_ADMIN_PASSWORD .env | cut -d= -f2)
echo '--- test delivery ---'
curl -s --noproxy '*' -u "gitea_admin:$PASS" -X POST \
  http://git.localhost/api/v1/repos/gitea_admin/ai-cicd-system/hooks/1/test -o /dev/null -w '%{http_code}\n'
sleep 3
echo '--- gitea 日志（webhook 相关） ---'
docker logs aisystem-gitea-1 --since 1m 2>&1 | grep -i webhook || echo "(无 webhook 日志行)"
echo '--- jenkins 日志 ---'
docker logs aisystem-jenkins-1 --since 1m 2>&1 | grep -i -E 'gitea|webhook' || echo "(无)"
