# ATR 终端运行时（terminal-runtime-skill）
# 构建上下文为项目根目录（见 docker-compose.yml）
FROM node:22-slim AS node-runtime

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

# tmux 后端 + 常用 TUI 测试程序 + agent CLI 运行底座（node/python/tmux，ADR-0017）
RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
        tmux git vim htop dialog fzf curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

COPY third_party/terminal-runtime-skill /opt/atr
RUN pip install --no-cache-dir -r /opt/atr/requirements.txt

ENV ATR_HOST=0.0.0.0 \
    ATR_PORT=18650 \
    ATR_DEFAULT_BACKEND=tmux

EXPOSE 18650
CMD ["python", "/opt/atr/scripts/terminal_runtime_service.py"]
