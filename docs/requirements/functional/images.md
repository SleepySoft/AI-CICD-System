# 功能需求：工具链与运行时镜像（IMG）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：构建/测试/浏览器镜像的功能需求；内容与构建机制见 `../../how/images-toolchain.md`

### FR-IMG-001 C/C++ 工具链镜像
- 状态: 生效 | 上层: UR-002 | 优先级: P1
- 描述: `toolchain-cpp` 含 gcc/clang、cmake、ninja、conan/vcpkg、ccache、gdb。
- 验收: 镜像内可完成示例 C++ 项目的 cmake 构建与调试。

### FR-IMG-002 Android 工具链镜像
- 状态: 生效 | 上层: UR-002 | 优先级: P1
- 描述: `toolchain-android` 含 JDK17、版本锁定的 SDK/NDK、Gradle 缓存卷；模拟器依赖 KVM 独立 profile。
- 验收: 镜像内可完成示例 Android 项目的 assemble 构建。

### FR-IMG-003 Node 工具链镜像
- 状态: 生效 | 上层: UR-002 | 优先级: P1
- 描述: `toolchain-node` 含 Node LTS（fnm 多版本）、pnpm、yarn、Playwright 依赖。
- 验收: 镜像内可完成示例前端项目的 install + build。

### FR-IMG-004 Python 测试镜像（Miniforge）
- 状态: 生效 | 上层: UR-002, NFR-001 | 优先级: P0
- 描述: `test-python` 基于 Miniforge 预建 conda 环境（pytest、pytest-xdist、allure、robotframework、hypothesis、coverage、requests、playwright）。
- 验收: 镜像内 `conda` 可用且无 defaults 通道；示例 pytest 套件跑通。

### FR-IMG-005 浏览器自动化镜像
- 状态: 生效 | 上层: UR-007 | 优先级: P1
- 描述: `browsers` 镜像提供 Playwright 三内核无头模式，及 Xvfb+x11vnc+noVNC 有头可视化模式。
- 验收: 无头模式可跑通示例脚本；有头模式可通过浏览器经 noVNC 观看执行过程。
