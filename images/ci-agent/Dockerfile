# CI Agent 轻量镜像：跑 chronicler 组件自检（契约 + 沙箱部署测试）
# 刻意精简（python + docker-cli + git）；重型测试环境仍是 test-python
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Asia/Shanghai

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends docker-cli git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
