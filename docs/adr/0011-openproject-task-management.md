# ADR-0011 任务管理：复用 OpenProject 工作包，AI 经 API 执行与回写

> 日期：2026-08-26 · 状态：已接受
> 关联：what/req-mgmt.md、what/manager.md；需求 BR-001、BR-003、NFR-001；ADR-0006

## 背景

环境缺一块"对标 Jira 的任务管理"。决策时刻已知的约束：

- 使用模式不是 Jira 式的"人布置、人执行、人流转"，而是**人提任务、AI 执行并标记状态**——任务系统必须 API/Webhook 完备，允许 Agent 领取任务、回写状态与结果，而非依赖人在 GUI 中操作每一步。
- 纯文本（markdown 任务清单）没有记录与统计能力：无状态历史、无负责人/工时字段、无报表，无法满足管理诉求。
- Jira 的核心价值在于把**需求、任务、提交、上下游关系**全部连接起来，选型必须覆盖这条追溯链，而不是只看"能不能建 ticket"。
- NFR-001（一票否决）：全部组件免费含商用。
- OpenProject 已按 ADR-0006 作为需求管理 GUI 层部署（requirements profile 按需启用）；Manager 已有 `task_run` 执行记录模型与 agent-runner 规划（what/manager.md §2.1，里程碑 M2）。

## 决策

任务管理**复用现有 OpenProject 实例**：以工作包（Work Package）为任务载体，与需求管理同实例；AI 执行闭环由 Manager 承担——经 OpenProject REST API / Webhook 领取任务，agent-runner 执行后回写状态与评论；提交关联经 Gitea 提交信息引用约定（`OP#<id>`）打通。不引入新的任务管理服务。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Jira | 商业付费，违反 NFR-001；工作流以人操作为中心，与"AI 执行和标记"的模式错位 |
| Plane（开源 Jira 替代品） | 功能与 OpenProject 高度重叠；引入第二个重量级服务，违背环境最小化原则 |
| Gitea Issues | 与提交/PR 原生关联是优势，但层级、上下游关系、统计报表能力弱；保留为降级方案（同 ADR-0006） |
| 纯文本任务清单（markdown） | 无状态历史、无统计报表，追溯链断裂，见背景 |
| Manager 自建任务管理 GUI | 自研 Jira 等价物属 Non-Goal，理由同 ADR-0006 否决自研需求管理 GUI |
| Redmine / Taiga 等其它开源 | 与 OpenProject 功能重叠，无增量价值；双系统徒增同步成本 |

## 后果

- 正面：需求与任务同实例，层级与上下游关系天然打通；OpenProject REST API/Webhook 完备，支撑"人提、AI 执行、AI 标记"；不新增服务与资源占用；需求↔任务↔提交追溯链闭合（需求层见 ADR-0006，提交层经 Gitea 引用约定）。
- 负面：OpenProject 并非为 AI 执行者设计，状态回写需人为约定（哪个状态由 Agent 改、评论格式）；提交↔任务关联依赖提交信息约定与 Gitea↔OpenProject 集成配置，弱于 Jira 原生链路；requirements profile 从"按需启用"变为常态启用，资源占用常态化。
- 待办（被接受后）：新增任务管理相关 FR 条目（任务领取、状态回写、提交关联约定）并更新 `requirements/traceability.md`；更新 `what/req-mgmt.md` 或拆出任务管理规格；Manager `task_run` 增加 OpenProject 工作包关联字段（随 M2/M3 落地）。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
