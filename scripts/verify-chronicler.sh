#!/usr/bin/env bash
# Chronicler supervisor 冒烟验证（宿主侧进程，ADR-0020）
set -u
BASE="${CHRONICLER_BASE:-http://127.0.0.1:8600}"

echo '--- supervisor 直连 ---'
curl --noproxy '*' -s -o /dev/null -w "GET /            -> %{http_code}\n" "$BASE/"
curl --noproxy '*' -s "$BASE/api/health"; echo

echo '--- 未登录访问受保护 API（应 401） ---'
curl --noproxy '*' -s -o /dev/null -w 'GET /api/projects -> %{http_code}\n' "$BASE/api/projects"
curl --noproxy '*' -s -o /dev/null -w 'GET /api/runs     -> %{http_code}\n' "$BASE/api/runs"
curl --noproxy '*' -s -o /dev/null -w 'GET /api/users    -> %{http_code}\n' "$BASE/api/users"

echo '--- 经 Caddy 入口（应 200/401，证明 app.localhost 已重接宿主） ---'
curl --noproxy '*' -s -o /dev/null -w 'app.localhost /            -> %{http_code}\n' -H 'Host: app.localhost' http://127.0.0.1/
curl --noproxy '*' -s -o /dev/null -w 'app.localhost /api/health  -> %{http_code}\n' -H 'Host: app.localhost' http://127.0.0.1/api/health

echo '--- docker 本地 socket 可达（工具面板前提） ---'
docker version --format 'server {{.Server.Version}}' && echo DOCKER-SOCK-OK
