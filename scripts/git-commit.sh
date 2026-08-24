#!/usr/bin/env bash
# 修正暂存区并提交
set -euo pipefail
cd /mnt/c/D/code/AI-CICD-System
git rm -r --cached --quiet homepage/config/logs homepage/config/settings.yaml homepage/config/kubernetes.yaml 2>/dev/null || true
git add -A
echo "---- 排除检查（应为空） ----"
git diff --cached --name-only | grep -E '\.env$|homepage/config/logs|settings\.yaml|kubernetes\.yaml' || echo CLEAN
echo "---- 提交 ----"
git commit -m "环境 + 管理服务 M1：Docker Compose 一体化研发环境与 Manager 管理台

环境（docker-compose.yml 为唯一事实源）：
- 核心栈：Caddy 入口 / Gitea / Jenkins(JCasC) / Keycloak SSO / Homepage / PostgreSQL / Redis
- 可选 profile：knowledge(Qdrant+Outline+MkDocs) / requirements(OpenProject) / monitor / localai / browsers
- 工具链镜像：toolchain-cpp / toolchain-android / toolchain-node / test-python(Miniforge) / browsers(noVNC)
- 预置 Keycloak realm（dev/boss 组 + OIDC 客户端）、Gitea/Manager 接线脚本、冒烟验证脚本

Manager（manager/，FastAPI + Vue3 SPA，OIDC 登录）：
- 工具总览：全环境工具集中面板（状态探测 / 跳转 / boss 可启停容器）
- Agent 终端：集成 terminal-runtime-skill(ATR) 会话控制（创建/截图/操作，boss 写 dev 读）

文档：docs/01 需求分析与选型、docs/02 管理服务设计、AGENTS.md、README"
git log --stat -1 | head -n 15
