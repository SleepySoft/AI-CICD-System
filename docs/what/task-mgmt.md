# 任务管理规格（OpenProject 工作包 + AI 执行回写）

> 版本：v1.0 · 日期：2026-08-26 · 状态：生效
> 定位：任务管理"人提、AI 执行、AI 标记"的对外契约；Non-Goals：不自建任务 GUI（ADR-0011）、不做定时导出与自动远端推送（ADR-0014）
> 关联需求：FR-TASK-001 ~ FR-TASK-005、BR-001、NFR-009

## 1. WHY

任务管理需要记录与统计（否决纯文本），且使用模式是"人提任务、AI 执行并标记"而非 Jira 式纯人工流转；同时要把需求、任务、提交、上下游串成追溯链。OpenProject 一个实例同时覆盖需求管理（req-mgmt.md）与任务管理。

## 2. WHAT

### 2.1 角色分工

| 角色 | 职责 | 边界 |
|------|------|------|
| 人 | 建任务、定优先级、验收关闭 | 仅人可置 `closed`（workflow 按角色限制，FR-TASK-003） |
| Agent | 领取、执行、回写状态与结果评论 | 不动非自己认领的任务；不改主题与需求关联 |
| Manager | 自动化侧：轮询/Webhook 领取 → agent-runner 执行 → API 回写 | 执行器随 M2/M3 落地，`task_run` 记录 `openproject_id` 关联 |

### 2.2 状态机约定

```
new → in progress（AI 认领，评论）→ done/to be reviewed（AI 回写，评论结果摘要）→ closed（仅人）
                └ 阻塞：状态不变，评论阻塞原因
```

状态清单与 href 以实例 `GET /api/v3/statuses` 为准，不硬编码；需要"待验收"等自定义状态时在 OpenProject 管理后台配置。

### 2.3 API 契约要点

- 认证：HTTP Basic，用户名固定 `apikey`，密码为个人 token（环境变量 `OPENPROJECT_API_KEY`，绝不入库）。
- 更新必带 `lockVersion`（乐观锁）；集合查询用 `filters`（URL 编码 JSON）+ `offset/pageSize` 分页。
- 操作细节与 curl 示例：`.agents/skills/openproject/SKILL.md`（Agent 与 Manager 代码共同遵守）。

### 2.4 关联契约

- 提交 ↔ 任务：提交信息携带 `OP#<工作包ID>`（FR-TASK-004）。
- 需求 ↔ 任务：需求条目在 Git（req-mgmt.md 机器可读层），工作包经描述/评论引用需求 ID；OpenProject 内用工作包关系表达上下游。
- 审计快照：`scripts/export-openproject.sh` 手工导出（FR-TASK-005，ADR-0014）；DB 运行态以 OpenProject 为准，快照入 Git 供审计（NFR-009）。

## 3. HOW

Agent 操作规范见 `.agents/skills/openproject/`；导出实现见 `scripts/export-openproject.sh`；Manager 领取-执行-回写管线随 M2/M3 落地（what/manager.md §里程碑）。部署见 ../how/deployment.md（requirements profile）。
