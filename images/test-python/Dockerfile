# Python 测试环境 —— Miniforge（conda-forge 通道，规避 Anaconda 商用授权风险）
FROM condaforge/miniforge3:latest

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai

# docker CLI（组件沙箱部署测试经宿主 docker.sock 驱动，FR-MGR-023）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends docker-cli ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# 预建测试环境 aisys-test
RUN mamba create -y -n aisys-test python=3.12 \
        pytest pytest-xdist pytest-timeout \
        allure-pytest robotframework \
        hypothesis coverage requests \
        playwright \
    && mamba clean -afy

# 让 conda 环境默认生效
ENV PATH=/opt/conda/envs/aisys-test/bin:${PATH}

# Playwright 浏览器依赖与浏览器本体（无头测试用）
RUN playwright install --with-deps chromium

WORKDIR /work
CMD ["pytest", "--version"]
