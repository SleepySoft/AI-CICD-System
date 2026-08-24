#!/usr/bin/env bash
# 检查 keycloak 9000 管理端口健康端点
set -u
docker exec aisystem-keycloak-1 bash -c 'exec 3<>/dev/tcp/localhost/9000 && printf "GET /health/ready HTTP/1.0\r\n\r\n" >&3 && head -c 200 <&3' || echo "PORT-9000-FAIL"
