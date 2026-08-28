#!/usr/bin/env bash
# 将 Chronicler supervisor 注册为 systemd 用户服务（ADR-0020：平台原生服务管理器托管）
# 用法: bash chronicler/scripts/install-service.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # chronicler/
REPO="$(dirname "$ROOT")"                         # 仓库根
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/chronicler.service" <<EOF
[Unit]
Description=Chronicler supervisor
After=docker.socket

[Service]
WorkingDirectory=$REPO
Environment=PYTHONUNBUFFERED=1
ExecStart=$ROOT/.venv/bin/python -m chronicler serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now chronicler
echo "已安装并启动。查看状态: systemctl --user status chronicler"
echo "开机自启（不需登录）: sudo loginctl enable-linger $USER"
