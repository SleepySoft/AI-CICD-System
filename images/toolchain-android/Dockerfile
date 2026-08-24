# Android 构建工具链（应用级：SDK/NDK + Gradle；AOSP 级请扩展）
FROM eclipse-temurin:17-jdk-noble

ENV DEBIAN_FRONTEND=noninteractive TZ=Asia/Shanghai
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

# 版本锁定：命令行工具与 SDK 组件
ARG CMDLINE_TOOLS_ZIP=commandlinetools-linux-11076708_latest.zip
ARG ANDROID_PLATFORM=android-34
ARG ANDROID_BUILD_TOOLS=34.0.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl wget unzip zip ca-certificates \
        python3 python3-pip \
        build-essential ninja-build cmake \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools \
    && curl -fsSL -o /tmp/cmdtools.zip \
        "https://dl.google.com/android/repository/${CMDLINE_TOOLS_ZIP}" \
    && unzip -q /tmp/cmdtools.zip -d ${ANDROID_HOME}/cmdline-tools \
    && mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && rm /tmp/cmdtools.zip

RUN yes | sdkmanager --licenses >/dev/null \
    && sdkmanager \
        "platform-tools" \
        "platforms;${ANDROID_PLATFORM}" \
        "build-tools;${ANDROID_BUILD_TOOLS}"

# Gradle 构建缓存卷（挂载后可跨构建复用）
VOLUME ["/root/.gradle"]

WORKDIR /work
CMD ["/bin/bash"]
