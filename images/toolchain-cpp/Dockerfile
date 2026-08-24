# C/C++ 工具链镜像（Jenkins 构建容器 / devcontainer 共用）
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ clang \
        cmake ninja-build ccache \
        gdb strace ltrace valgrind \
        git curl wget ca-certificates \
        pkg-config autoconf automake libtool \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# conan 2 包管理（Ubuntu 24.04 需 --break-system-packages）
RUN pip3 install --no-cache-dir --break-system-packages conan \
    && conan profile detect --force

WORKDIR /work
CMD ["/bin/bash"]
