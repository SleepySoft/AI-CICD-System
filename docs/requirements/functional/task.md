# 功能需求：任务管理（TASK）

> 版本：v1.0 · 日期：2026-08-26 · 状态：生效
> 定位：任务管理（人提、AI 执行、AI 标记）的可验收需求；规格见 `../../what/task-mgmt.md`，决策见 `../../adr/0011-openproject-task-management.md`

### FR-TASK-001 任务前端提交
- 状态: 生效 | 上层: BR-001 | 优先级: P0
- 描述: 人在 OpenProject GUI 创建工作包作为任务（主题、描述、优先级、指派人）。
- 验收: 创建后可经 API v3 检索到该工作包且上述字段完整。

### FR-TASK-002 AI 任务领取
- 状态: 生效 | 上层: BR-001 | 优先级: P0
- 描述: Agent 经 OpenProject API 按状态/指派筛选待执行任务并认领（置 in progress 并评论认领）。
- 验收: 按 `.agents/skills/openproject/` 约定操作，Agent 可列出待领任务并成功将领到的任务置为 in progress。

### FR-TASK-003 AI 状态回写与结果评论
- 状态: 生效 | 上层: BR-001 | 优先级: P0
- 描述: Agent 执行完成后将工作包置为约定完成态并评论结果摘要与产出位置；`closed` 状态仅人可设置（OpenProject workflow 按角色限制）。
- 验收: PATCH 带 lockVersion 回写成功且评论落库；以 Agent 身份尝试置 closed 被 workflow 拒绝。

### FR-TASK-004 任务↔提交关联
- 状态: 生效 | 上层: BR-001 | 优先级: P1
- 描述: 提交信息携带 `OP#<工作包ID>`，提交与工作包可互相定位。
- 验收: 抽查含 `OP#<id>` 的提交可反查到对应工作包，且工作包评论/链接可定位到该提交。

### FR-TASK-005 任务数据手工导出快照
- 状态: 生效 | 上层: BR-001 | 优先级: P1
- 描述: `scripts/export-openproject.sh` 手工一键产出任务数据快照（JSON 全量 + Markdown 摘要），供审计与 AI 离线文本视图。
- 验收: 运行脚本产出带时间戳的快照目录，INDEX.md 列出项目与工作包计数（决策见 `../../adr/0014-openproject-manual-export.md`）。
