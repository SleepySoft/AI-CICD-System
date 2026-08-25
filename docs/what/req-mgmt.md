# 需求管理工具链规格（OpenProject + 需求即代码）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：需求管理的双层规格——GUI 层与机器可读层的分工与同步契约
> 关联需求：FR-REQ-001 ~ FR-REQ-003、BR-003

## 1. WHY

BR-003（Agent 比对代码与需求）要求需求**机器可读**；同时团队需要 GUI 管理需求状态与层级。Jama 无开源等价物，故采用两层组合。

## 2. WHAT

| 层 | 工具 | 职责 |
|----|------|------|
| 管理界面 | OpenProject CE | 需求条目、状态、看板、层级、API |
| 机器可读层 | 带 ID 的结构化文本进 Git（Sphinx-Needs，或本仓库 `../requirements/` 的 markdown 方案） | 需求条目化 + 自动生成需求↔代码↔测试追踪矩阵 |

同步契约：

- 机器可读层是 Agent 的输入（FR-REQ-001）：条目必须含稳定 ID 与状态字段，可导出 JSON。
- OpenProject 经 API 与机器可读层双向同步（FR-REQ-003）。
- 本仓库自身的项目需求直接采用 `docs/requirements/`（markdown + ID）方案，即机器可读层的最小实现；追踪矩阵见 `../requirements/traceability.md`。

降级方案：纯 Gitea Issue + markdown 需求模板（部署向导可选）。

## 3. HOW

部署见 ../how/deployment.md（requirements profile）；选型决策见 ../adr/0006-openproject-sphinx-needs.md。
