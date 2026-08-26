#!/usr/bin/env bash
# 从备份恢复（离线操作：会先停栈并覆盖数据目录，需确认）
# 用法: bash scripts/restore.sh <备份目录> [--yes]
set -euo pipefail
cd "$(dirname "$0")/.."

BK="${1:?用法: bash scripts/restore.sh <备份目录> [--yes]}"
YES="${2:-}"
DATA_ROOT="${DATA_ROOT:-./data}"
PGUSER="${POSTGRES_USER:-aisys}"
[ -d "$BK" ] || { echo "备份目录不存在: $BK"; exit 1; }

echo ">> 备份内容:"
ls -lh "$BK"
if [ "$YES" != "--yes" ]; then
  read -rp "恢复将停止全部服务并覆盖 $DATA_ROOT，确认？[y/N] " a
  [ "${a:-}" = y ] || { echo "已取消"; exit 1; }
fi

# 1. 停栈（显式服务名，绕过 profile 过滤）
SVCS="$(docker compose ps --services --status running 2>/dev/null || true)"
[ -n "$SVCS" ] && { echo ">> 停止服务: $SVCS"; docker compose stop $SVCS; }

# 2. 文件数据
if [ -f "$BK/data-all.tar.gz" ]; then
  echo ">> 整体恢复数据目录（离线备份）"
  rm -rf "${DATA_ROOT:?}"
  mkdir -p "$DATA_ROOT"
  tar -xzf "$BK/data-all.tar.gz" -C "$DATA_ROOT"
else
  for f in "$BK"/*.tar.gz; do
    [ -e "$f" ] || continue
    svc="$(basename "$f" .tar.gz)"
    echo ">> 恢复 $svc"
    rm -rf "${DATA_ROOT:?}/$svc"
    tar -xzf "$f" -C "$DATA_ROOT"
  done
fi

# 3. Postgres：离线备份已含原始数据目录则跳过；在线备份用逻辑导出灌库
if [ -f "$BK/postgres.sql" ] && [ ! -f "$BK/data-all.tar.gz" ]; then
  echo ">> 启动 postgres 并灌库"
  docker compose up -d postgres
  for _ in $(seq 1 30); do
    docker compose exec -T postgres pg_isready -U "$PGUSER" >/dev/null 2>&1 && break
    sleep 2
  done
  docker compose exec -T postgres psql -U "$PGUSER" -d postgres -f - < "$BK/postgres.sql"
fi

# 4. 拉起全栈
docker compose up -d
echo "OK 恢复完成。验证: bash scripts/verify.sh && bash scripts/verify-manager.sh"
