#!/usr/bin/env bash
# 一键备份（ADR-0015）
#   默认在线模式：不影响服务 —— Postgres 逻辑导出（pg_dumpall，在线一致）
#                  + 文件级打包其余数据目录
#   --stop 离线模式：停止全部容器后整体打包 data/（强一致，含 postgres 原始目录），
#                    完成后自动恢复原运行中的服务
# 用法: bash scripts/backup.sh [--stop] [输出目录]      默认输出 backups/<时间戳>/
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=online
[ "${1:-}" = "--stop" ] && { MODE=stop; shift; }
DATA_ROOT="${DATA_ROOT:-./data}"
OUT="${1:-${BACKUP_ROOT:-./backups}}/$(date +%Y%m%d-%H%M%S)"
PGUSER="${POSTGRES_USER:-aisys}"
mkdir -p "$OUT"

echo ">> 模式: $MODE | 数据目录: $DATA_ROOT | 输出: $OUT"

# 1. Postgres 逻辑全量导出（在线一致；--clean 使恢复可覆盖既有库）
if [ -n "$(docker compose ps -q postgres 2>/dev/null)" ]; then
  echo ">> 导出 Postgres（pg_dumpall，不影响服务）"
  docker compose exec -T postgres pg_dumpall -U "$PGUSER" --clean --if-exists > "$OUT/postgres.sql"
else
  echo "!! postgres 未运行，跳过逻辑导出"
fi

# 2. 文件数据打包
if [ "$MODE" = stop ]; then
  SVCS="$(docker compose ps --services --status running)"
  echo ">> 停止服务: ${SVCS:-无}"
  [ -n "$SVCS" ] && docker compose stop $SVCS
  tar -czf "$OUT/data-all.tar.gz" -C "$DATA_ROOT" .
  [ -n "$SVCS" ] && docker compose start $SVCS
  echo ">> 服务已恢复启动（健康就绪需数十秒）"
else
  for d in "$DATA_ROOT"/*/; do
    [ -d "$d" ] || continue
    svc="$(basename "$d")"
    # 在线模式下活库目录拷贝无一致性保证，postgres 以 dump 为准
    [ "$svc" = postgres ] && continue
    echo ">> 打包 $svc"
    tar -czf "$OUT/$svc.tar.gz" -C "$DATA_ROOT" "$svc"
  done
fi

# 3. 清单（逐子系统列出覆盖方式，便于审计核对）
{
  echo "time: $(date -Iseconds)"
  echo "mode: $MODE"
  echo "data_root: $DATA_ROOT"
  echo "coverage:"
  if [ "$MODE" = stop ]; then
    echo "  all: data-all.tar.gz（含 postgres 原始目录，全子系统强一致）"
  else
    [ -f "$OUT/postgres.sql" ] && \
      echo "  postgres: postgres.sql（pg_dumpall 全实例，含 gitea/keycloak/outline/openproject 等全部库）"
    for d in "$DATA_ROOT"/*/; do
      [ -d "$d" ] || continue
      svc="$(basename "$d")"
      [ "$svc" = postgres ] && continue
      if [ -f "$OUT/$svc.tar.gz" ]; then
        echo "  $svc: $svc.tar.gz"
      else
        echo "  $svc: !! 未打包"
      fi
    done
  fi
  ls -lh "$OUT"
} > "$OUT/manifest.txt"

echo "OK -> $OUT"
du -sh "$OUT"
