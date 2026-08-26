#!/usr/bin/env bash
# aider 安装脚本（ADR-0017：后装到持久卷，锁版本，幂等）
# 在 terminal-runtime 容器内执行：bash /opt/agent-install/aider.sh
set -euo pipefail

NAME="aider"
VERSION="0.86.1"                      # 锁版本：升级 = 改这里 + agents.yaml 无需动
PREFIX="/opt/agents/${NAME}"
PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"

export HOME="${PREFIX}"               # 登录态/配置随持久卷保留
mkdir -p "${PREFIX}"

if [ -f "${PREFIX}/VERSION" ] && [ "$(cat "${PREFIX}/VERSION")" = "${VERSION}" ]; then
    echo "[install] ${NAME} ${VERSION} 已安装，跳过"
    exit 0
fi

echo "[install] 安装 ${NAME}==${VERSION} 到 ${PREFIX} ..."
python -m venv "${PREFIX}"
"${PREFIX}/bin/pip" install --no-cache-dir -i "${PIP_INDEX}" "aider-chat==${VERSION}"

echo "${VERSION}" > "${PREFIX}/VERSION"
echo "[install] 完成：${PREFIX}/bin/aider"
