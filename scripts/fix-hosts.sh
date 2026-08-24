#!/usr/bin/env bash
# 向 /etc/hosts 写入 AISystem 子域名（WSL 内 *.localhost 不解析时需要）
# 用法: sudo ./scripts/fix-hosts.sh
set -euo pipefail
hosts="portal git ci sso kb docs req vectors status browser llm"
for h in $hosts; do
  entry="127.0.0.1 ${h}.localhost"
  grep -q "${h}.localhost" /etc/hosts || echo "$entry" >> /etc/hosts
done
echo "hosts 已更新:"; grep localhost /etc/hosts
