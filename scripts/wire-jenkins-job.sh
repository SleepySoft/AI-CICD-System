#!/usr/bin/env bash
# 创建/更新 Jenkins 任务（经 REST 投递 config.xml，幂等）
# 为什么不用 JCasC jobs：job-dsl 脚本语法错误会让 Jenkins 启动即崩溃循环（2026-08-29 实测），
# REST 投递在启动后执行，失败只影响任务不影响 Jenkins 本体。
# 用法: bash scripts/wire-jenkins-job.sh   （Jenkins 需已 healthy）
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

U="${JENKINS_ADMIN_ID:-admin}"
P="${JENKINS_ADMIN_PASSWORD:?}"
H="Host: ci.localhost"
B=http://127.0.0.1
JOB=chronicler-selftest

echo "==> 等待 jenkins 就绪"
for i in $(seq 1 40); do
  code=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' -u "$U:$P" -H "$H" "$B/api/json" || true)
  [ "$code" = "200" ] && break
  sleep 5
done

JAR=$(mktemp)
CRUMB=$(curl --noproxy '*' -s -c "$JAR" -u "$U:$P" -H "$H" "$B/crumbIssuer/api/json" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["crumbRequestField"]+": "+d["crumb"])')

if curl --noproxy '*' -s -o /dev/null -u "$U:$P" -H "$H" "$B/job/$JOB/api/json" -w '%{http_code}' | grep -q 200; then
  echo "==> 任务已存在，更新配置"
  curl --noproxy '*' -s -b "$JAR" -u "$U:$P" -H "$H" -H "$CRUMB" -X POST "$B/job/$JOB/config.xml" \
    -H "Content-Type: application/xml" --data-binary "@jenkins/jobs/$JOB.xml" -o /dev/null -w 'update: %{http_code}\n'
else
  echo "==> 创建任务"
  curl --noproxy '*' -s -b "$JAR" -u "$U:$P" -H "$H" -H "$CRUMB" -X POST "$B/createItem?name=$JOB" \
    -H "Content-Type: application/xml" --data-binary "@jenkins/jobs/$JOB.xml" -o /dev/null -w 'create: %{http_code}\n'
fi

echo "==> 触发分支扫描"
curl --noproxy '*' -s -b "$JAR" -u "$U:$P" -H "$H" -H "$CRUMB" -X POST "$B/job/$JOB/build" -o /dev/null -w 'scan: %{http_code}\n'
rm -f "$JAR"
