# 工具链镜像机制

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：构建/测试/浏览器镜像的内容与构建机制；功能需求见 ../requirements/functional/images.md 与 ci.md
> 关联需求：FR-IMG-001 ~ FR-IMG-005、FR-CI-001 ~ FR-CI-004、NFR-005

## 1. WHY / WHAT 摘要

构建环境必须容器化、版本锁定、可复现（NFR-005），并同时服务 CI 流水线与本地 devcontainer。

## 2. HOW

### 2.1 镜像清单

| 镜像 | 内容 |
|------|------|
| `toolchain-cpp` | gcc/clang、cmake、ninja、conan/vcpkg、ccache、gdb |
| `toolchain-android` | JDK17、Android cmdline-tools + SDK/NDK（版本锁定）、Gradle 缓存卷 |
| `toolchain-node` | Node LTS（fnm 多版本）、pnpm、yarn、Playwright 依赖 |
| `test-python` | Miniforge + 预建 conda 环境（pytest、pytest-xdist、allure、robotframework、hypothesis、coverage、requests、playwright） |
| `browsers` | Playwright 三内核（无头）；同容器 Xvfb + x11vnc + noVNC（有头可视化） |

### 2.2 构建与分发机制

- 全部以 `images/*/Dockerfile` 版本锁定；`scripts/build-images.sh`（Windows 用 `build-images.ps1`）统一构建。
- 镜像推送到 Gitea 内置 Docker registry（同时承接 BR-005 的包注册需求）。
- 对外发布 `.devcontainer` 配置，VS Code 可直接挂入同一环境。

### 2.3 CI 集成机制

- Jenkins Controller + **Docker inbound agents**：构建在一次性容器中执行，环境即上述工具链镜像（FR-CI-002）。
- **JCasC + plugins.txt** 把 Jenkins 全部配置固化进镜像（FR-CI-004），可重建。
- 测试报告用 **Allure** 统一聚合，经 `allure-jenkins-plugin` 接回 Jenkins（FR-CI-003）。
- Playwright 既是测试框架又是 Agent 浏览器工具（playwright-mcp），一镜两用。

### 2.4 已知机制约束

- Android 模拟器依赖 KVM，WSL 下默认不启用（独立 profile）。
- Miniforge 仅 conda-forge 通道（授权背景见 ../why/licensing.md，决策见 ../adr/0003-miniforge-replaces-anaconda.md）。
