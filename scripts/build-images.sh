#!/usr/bin/env bash
# 构建全部工具链镜像（在 WSL / Linux 中执行）
# 用法: ./scripts/build-images.sh [镜像名...]   # 不带参数则构建全部
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGES=(toolchain-cpp toolchain-android toolchain-node test-python browsers)
TARGETS=("$@")
if [ ${#TARGETS[@]} -eq 0 ]; then
  TARGETS=("${IMAGES[@]}")
fi

for img in "${TARGETS[@]}"; do
  if [ -d "images/${img}" ]; then
    echo "==> 构建 aisystem/${img}:latest"
    docker build -t "aisystem/${img}:latest" "images/${img}"
  else
    echo "!! 未知镜像: ${img}（可选: ${IMAGES[*]}）" >&2
    exit 1
  fi
done
echo "==> 完成。查看: docker images | grep aisystem"
