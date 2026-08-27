# ADR-0020 Manager 移出 Docker：docker 宿主侧 supervisor（推翻 ADR-0019）

> 日期：2026-08-27 · 状态：已接受
> 关联：how/manager-architecture.md §2.5（部署形态）；需求 NFR-001、NFR-005、NFR-008、BR-009、FR-MGR-001；ADR-0012、ADR-0017、ADR-0019（被推翻）、ADR-0021（配套）

## 背景

ADR-0019 曾决策"Manager 保持容器化 + Windows 极简宿主引导器"。落地前复核发现其前提与设计目标均已变化：

- **0019 的经验前提失准**：复检本机环境，发行版内无 docker.service、无 dockerd 二进制，`docker` 命令实为 Docker Desktop shim——"WSL2 空闲 60s 回收 VM 杀死栈"发生于 dockerd 非常驻服务时；dockerd 以 systemd 常驻后 VM 始终有活进程，回收场景构造性消失（`vmIdleTimeout=-1` 仅作双保险）。
- **Manager 定位升级**：它不止管理组件，还要规划/指导 agent 对代码与文档资产做分析（supervisor）。资产在宿主，容器内 Manager 与资产之间永远隔一层路径翻译（`C:\...` ↔ `/mnt/c/...` ↔ 容器挂载路径），每加一层多一处出错点。
- **宿主可达性已验证**：全部工具 API 经 Caddy 暴露于 `*.localhost`；Keycloak 已开 `KC_HOSTNAME_BACKCHANNEL_DYNAMIC`，backchannel 可走 `sso.localhost`——宿主进程消费这些 API 无需新开端口、不破坏 ATR 安全边界。
- **多平台要求**：Windows（Docker Desktop 或 WSL 原生 dockerd）、Linux、macOS 均需支持，统一原则为"在哪个环境跑，就用哪个环境的 docker"。
- NFR-001：Docker Desktop 对大组织商用付费，只能作为用户已有许可时的可选路径；WSL/原生 dockerd 保留为免费默认。
- 0019 设想的引导器（开机自启、探活、救栈）与宿主 Manager 的控栈职责天然同构。

## 决策

**Manager 移出 compose，成为部署在 docker 宿主侧的 supervisor 进程**（Python 实现，M6 Nuitka 二进制化不变）：跟随 dockerd 同环境部署，经本地 Docker API（unix socket / npipe，按平台解析，尊重 `DOCKER_HOST` 与显式配置）控制栈；吸收 0019 引导器的全部职责（开机自启、探活、`up.sh` 恢复），引导器不再作为独立件存在。部署推荐 Linux/WSL，macOS 等同支持，Windows 可用但不推荐；生命周期由平台原生服务管理器托管（systemd / launchd / 任务计划），supervisor 不维护任何跨边界会话（WSL 生命周期交 systemd）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持 ADR-0019（容器化 + Windows 引导器） | 路径翻译层永久存在，supervisor 定位无法满足；引导器与 Manager 双进程职责重叠；Windows→WSL 跨界调用脆弱（转义 / proxy / 计划任务会话差异） |
| Manager 出容器但固定部署 Windows | WSL docker 场景需跨 `wsl.exe` 边界控栈，或为 dockerd 开 tcp:2375 无认证端口（等同暴露 root 级 API，比 sock 挂载更差） |
| supervisor 与引导器拆为两个进程 | 探活/恢复/控栈职责同构，拆分只增进程间协调复杂度 |

## 后果

- 正面：agent 获得真实宿主路径（配套 ADR-0021）；调试 = 本地进程（IDE 直跑、断点、热重载，容器调试三件套不再需要）；docker 控制永远走本地 socket，无 2375 暴露面；引导器消失，架构组件数净减一；四平台部署对称。
- 负面：交付变两段式（compose 栈 VM 镜像 + supervisor 安装器），NFR-005 措辞需修订；compose 不再是全部系统的事实源（栈仍是，supervisor 在外）；密钥/配置由 supervisor 在宿主直读 `.env`，散落面较容器环境变量略增；OIDC 回调与 Caddy `app.localhost` 路由需重接（指向宿主进程或 supervisor 直监听宿主端口）。
- 待办：supervisor 安装器与各平台服务注册；Caddy/OIDC 重接；docker compose 移除 manager 服务；M2 起路线图按 supervisor 形态重排。
- 同步：ADR-0019 状态标注被本篇推翻；how/manager-architecture.md §2.5/§3 改写为现状；what/manager.md、requirements/non-functional.md（NFR-001 许可注记、NFR-005 两段式）、traceability.md、runbooks/deploy.md、docs/README.md 索引。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
