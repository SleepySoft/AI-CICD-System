# ATR 终端运行时（terminal-runtime-skill）
# 构建上下文为项目根目录（见 docker-compose.yml）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

# tmux 后端 + 常用 TUI 测试程序 + agent CLI 运行底座（node/python/tmux，ADR-0017；使用国内镜像源加速）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        tmux git vim htop dialog fzf curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/terminal-runtime-skill /opt/atr
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r /opt/atr/requirements.txt

ENV ATR_HOST=0.0.0.0 \
    ATR_PORT=18650 \
    ATR_DEFAULT_BACKEND=tmux

EXPOSE 18650
CMD ["python", "/opt/atr/scripts/terminal_runtime_service.py"]
