# Node.js 前后端工具链
FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

# pnpm / yarn / 常用全局工具（corepack 随 Node 22 内置）
RUN corepack enable \
    && corepack prepare pnpm@latest --activate \
    && npm install -g typescript ts-node serve

WORKDIR /work
CMD ["node"]
