# 环境规格（compose 服务与域名契约）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：环境对外可见的规格与契约——服务清单、域名、profile、资源分档；内部机制见 ../how/deployment.md
> 关联需求：FR-ENV-001 ~ FR-ENV-005、NFR-003、NFR-006、NFR-008、NFR-009

## 1. WHY

环境需要对用户与 Agent 暴露稳定的访问契约（域名、账号、可见性），契约变动会影响所有入口文档与接线脚本。

## 2. WHAT

### 2.1 服务清单与域名契约

| 服务 | 域名 | profile | 默认账号 |
|------|------|---------|---------|
| Homepage 门户 | http://portal.localhost | 核心 | - |
| Gitea | http://git.localhost | 核心 | `scripts/wire-sso.sh` 创建管理员 |
| Jenkins | http://ci.localhost | 核心 | `.env` 的 `JENKINS_ADMIN_ID/PASSWORD` |
| Keycloak | http://sso.localhost/admin | 核心 | `.env` 的 `KEYCLOAK_ADMIN/PASSWORD` |
| Manager | http://app.localhost | 核心 | Keycloak 登录 |
| terminal-runtime (ATR) | http://term.localhost/ui | 核心 | - |
| Outline 知识库 | http://kb.localhost | knowledge | Keycloak 登录（预置 boss/dev） |
| MkDocs 文档站 | http://docs.localhost | knowledge | - |
| OpenProject | http://req.localhost | requirements | 首启创建管理员 |
| Uptime Kuma | http://status.localhost | monitor | 首启创建管理员 |
| noVNC 浏览器 | http://browser.localhost | browsers | - |

> `*.localhost` 在现代浏览器自动解析到 127.0.0.1；不生效时写 hosts。

### 2.2 profile 契约

`core`（无标记，默认）/ `knowledge` / `requirements` / `monitor` / `localai` / `browsers`。重负载组件（Android 构建、本地模型）必须挂 profile，默认不启动（NFR-003）。

### 2.3 SSO 契约

Keycloak 预置 realm：组 `dev` / `boss`；token 的 `groups` claim 为各系统的角色映射依据。Manager 客户端由 `scripts/wire-manager.sh` 注册。

### 2.4 资源分档（NFR-003）

| 场景 | CPU | 内存 | 磁盘 | 说明 |
|------|-----|------|------|------|
| 最小（core，无 Android 构建） | 4C | 8 GB | 60 GB | Gitea+Jenkins+门户 |
| 推荐（含 Node/C++ 构建、知识库全量） | 8C | 16 GB | 150 GB | 日常团队使用 |
| 完整（含 Android 编译、本地 embedding） | 16C | 32 GB+ | 300 GB+ SSD | Android 构建建议独立节点或夜间构建 |

### 2.5 数据持久化契约（NFR-008、NFR-009）

- **显式落宿主**（ADR-0012）：所有持久化数据 bind mount 到 `${DATA_ROOT:-./data}/<服务名>`（已落实于 compose），禁用命名卷存业务数据；升级 = 只重建容器，数据目录不动。
- **Git 为事实源**（ADR-0013）：可文本化数据（配置、文档、需求、Prompt、报告、知识、任务元数据）以 Git 仓库为事实源；DB（Postgres 各库）与二进制数据（向量索引、镜像、构建产物）仅作可重建/可导出的运行时层。
- **备份**（ADR-0015）：一键双模式脚本（在线 dump+打包 / 停服整体打包），操作见 ../runbooks/backup-restore.md。

## 3. HOW

编排与部署机制见 ../how/deployment.md；compose 文件本身是可执行事实源。
