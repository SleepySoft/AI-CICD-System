# CI Agent 轻量镜像：跑 chronicler 组件自检（契约 + 沙箱可达性测试）
# 刻意精简（python + docker-cli + compose 插件 + git）；重型测试环境仍是 test-python
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

# docker compose v2 插件：沙箱机制（python -m chronicler sandbox）依赖；
# Debian 13 仓库无 docker-compose-v2 包，从官方 docker:29-cli 镜像拷贝（与宿主 daemon 29.x 同代）
COPY --from=docker:29-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends docker-cli git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
