# 环境规格（组件服务与域名契约）

> 版本：v1.1 · 日期：2026-09-01 · 状态：生效
> 定位：环境对外可见的规格与契约——服务清单、域名、启停契约、资源分档；内部机制见 ../how/deployment.md
> 关联需求：FR-ENV-001 ~ FR-ENV-005、NFR-003、NFR-006、NFR-008、NFR-009

## 1. WHY

环境需要对用户与 Agent 暴露稳定的访问契约（域名、账号、可见性），契约变动会影响所有入口文档与接线脚本。

## 2. WHAT

### 2.1 服务清单与域名契约

| 组件 | 域名 | 启停 | 默认账号 |
|------|------|------|---------|
| Chronicler（supervisor） | http://app.localhost | 主入口 `python -m chronicler serve`（缺 .env 提示退出，ADR-0029） | 本地账密（create-admin）或 Keycloak OIDC |
| Caddy 统一入口 | -（反代） | autostart | - |
| Gitea | http://git.localhost | autostart | `scripts/wire-sso.sh` 创建管理员 |
| Jenkins | http://ci.localhost | autostart | `.env` 的 `JENKINS_ADMIN_ID/PASSWORD` |
| Keycloak | http://sso.localhost/admin | autostart | `.env` 的 `KEYCLOAK_ADMIN/PASSWORD` |
| PostgreSQL / Redis | -（内部） | autostart | `.env` 的 `POSTGRES_USER/PASSWORD` |
| Outline 知识库 | http://kb.localhost | 按需部署 | Keycloak 登录（预置 boss/dev） |
| MkDocs 文档站 | http://docs.localhost | 按需部署 | - |
| OpenProject | http://req.localhost | 按需部署 | 首启创建管理员 |
| Uptime Kuma | http://status.localhost | 按需部署 | 首启创建管理员 |
| Qdrant | http://vectors.localhost/dashboard | 按需部署 | - |
| Ollama | http://llm.localhost | 按需部署 | - |
| noVNC 浏览器 | http://browser.localhost | 按需部署 | - |
| terminal-runtime (ATR) | http://term.localhost/ui | 按需部署（可选沙箱，ADR-0021） | - |

> `*.localhost` 在现代浏览器自动解析到 127.0.0.1；不生效时写 hosts。

### 2.2 启停契约

根 docker-compose.yml 与 profile 已废除（ADR-0027）：组件 `plugin.yaml` 的 `autostart: true` 标记随 supervisor 启动自动拉起（FR-MGR-022），其余组件在首页工具面板按需部署/启停（admin；普通用户只读）。重负载组件（Android 构建、本地模型等）默认不自启（NFR-003）。

### 2.3 SSO 契约

Keycloak 预置 realm：组 `dev` / `boss`；token 的 `groups` claim 为各系统的角色映射依据。Chronicler 客户端由 `scripts/wire-chronicler.sh` 注册（可选 OIDC 后端，ADR-0023）。

### 2.4 资源分档（NFR-003）

| 场景 | CPU | 内存 | 磁盘 | 说明 |
|------|-----|------|------|------|
| 最小（autostart 核心，无 Android 构建） | 4C | 8 GB | 60 GB | Gitea+Jenkins+门户 |
| 推荐（含 Node/C++ 构建、知识库全量） | 8C | 16 GB | 150 GB | 日常团队使用 |
| 完整（含 Android 编译、本地 embedding） | 16C | 32 GB+ | 300 GB+ SSD | Android 构建建议独立节点或夜间构建 |

### 2.5 数据持久化契约（NFR-008、NFR-009）

- **显式落宿主 + public/private/workspace 三层**（ADR-0012/0026）：所有持久化数据 bind mount 到 `${DATA_ROOT:-./data}/`——`public/` 为组件交换区（挂所有容器 `/public`，谁建谁拥有、读人随意写人禁止），`private/<组件名>/` 仅挂载声明它的组件（API 型组件默认 private，文件型产物用 public），`workspace/` 为工作区（工程克隆等可由 git 重建的内容，不进备份）；机密永不落 data。升级 = 只重建容器，数据目录不动。
- **Git 为事实源**（ADR-0013）：可文本化数据（配置、文档、需求、Prompt、报告、知识、任务元数据）以 Git 仓库为事实源；DB（Postgres 各库）与二进制数据（向量索引、镜像、构建产物）仅作可重建/可导出的运行时层。
- **备份**（ADR-0015/0027）：`python -m chronicler backup` 组件化编排（组件 `hooks/backup.py` 声明自身覆盖范围），操作见 ../runbooks/backup-restore.md。

## 3. HOW

编排与部署机制见 ../how/deployment.md；组件目录（compose.yml + plugin.yaml）是可执行事实源（ADR-0027）。
