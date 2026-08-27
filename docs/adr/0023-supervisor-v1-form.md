# ADR-0023 supervisor v1 形态：SQLite + 本地账密 + 一次性会话（单机瘦身落地）

> 日期：2026-08-27 · 状态：已接受
> 关联：what/manager.md（数据模型/权限规格）；需求 FR-MGR-017、NFR-002、NFR-008；ADR-0020（宿主侧前提）、ADR-0021（会话语义）、ADR-0022（闭环其悬置的"单机瘦身"项）

## 背景

ADR-0020/0021/0022 之后 supervisor（Chronicler）开始 v1 实现，三个形态问题必须拍板：

1. **存储**：what/manager.md 原契约是 Postgres（库 manager），但 ADR-0022 已将 compose 栈降为可选底座——supervisor 不能硬依赖一个可选组件，否则"无底座独立运行"不成立。
2. **鉴权**：FR-MGR-017 要求分角色（admin/user）且后端可插拔；ADR-0022 把"Keycloak→本地账密"记录为悬置项。Keycloak 同属可选底座，v1 需要一个零依赖默认后端。
3. **agent 会话**：ADR-0021 标注持久/resume 语义为唯一 TBD；各家 harness 会话能力差异大，v1 必须选一个可立即落地的语义。

## 决策

1. **v1 存储用 SQLite**（stdlib sqlite3，WAL），数据落 `data/chronicler/`（NFR-008）；表名与 what/manager.md 契约保持同名（users/projects/task_runs/audit_log），未来迁移 Postgres 时只换驱动不改模型。
2. **v1 默认鉴权后端为本地账密**（PBKDF2 哈希 + itsdangerous 签名 cookie），鉴权抽象为接口，Keycloak OIDC 作为可插拔后端预留——ADR-0022 的"单机瘦身"项就此闭环：默认单机形态 = SQLite + 本地账密。
3. **v1 agent 会话仅支持一次性（once）**：harness 注册表声明会话能力，声明 `persistent` 的暂拒绝执行；resume/持久会话语义随 supervisor 内嵌 ATR 抽象模块一并设计（后续版本）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| v1 直接上 Postgres | 违背 ADR-0022"底座可选"：supervisor 独立运行的最小形态被 DB 服务绑架 |
| v1 默认接 Keycloak OIDC | 同上，Keycloak 属可选底座；本地账密兜底后，OIDC 可作为后端插回（FR-MGR-017 验收已覆盖双后端） |
| v1 即实现持久/resume 会话 | ADR-0021 明确语义 TBD；各家 harness 能力不一，未做抽象前硬接=追债 |
| 配置也入库（SQLite） | 注册表 YAML 文件热更新已被 ADR-0018 验证，人工改文件即可，v1 不做配置 CRUD 界面 |

## 后果

- 正面：supervisor 零外部服务依赖即可运行（只需 python + git + 可选 dockerd）；备份只需拷 `data/chronicler/`；本地账密使 demo/试用零接线。
- 负面：SQLite 并发写有限（v1 单进程足够；多实例部署需迁 Postgres）；本地账密无 MFA/密码策略，暴露公网时必须换 OIDC 后端（NFR-002 边界）；一次性会话丢失跨任务上下文（已知取舍，resume 语义后续补）。
- 同步：what/manager.md 数据模型节标注 v1 存储实现；requirements/non-functional.md NFR-002 补"本地账密仅限内网"边界；traceability.md FR-MGR-017 行指向 chronicler/。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
