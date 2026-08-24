# Python 测试环境 —— Miniforge（conda-forge 通道，规避 Anaconda 商用授权风险）
FROM condaforge/miniforge3:latest

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai

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
