# ADR-0028 持久产物统一入 shadow project（分析报告与蒸馏文档同仓版本化）

> 日期：2026-08-29 · 状态：已接受
> 关联：what/manager.md §2.1.1（Run 档案契约）；需求 FR-MGR-013、FR-MGR-005、NFR-009；ADR-0026（数据布局）、ADR-0022

## 背景

Run 档案契约（§2.1.1）落地后发现产物管理分裂：分析报告散在 `data/public/reports/<pid>/`（纯文件、无版本、无法回溯历史），蒸馏卡片进 shadow 库（git 版本化、可推送远端）。讨论确立的原则：**一次性/运行态产物丢弃，持久有价值的全部进 shadow project**。

决策时刻已知约束：

- shadow 库已在 `data/public/shadow/`（公交换区，ADR-0026），容器可挂载只读消费；
- FR-MGR-013 要求产物可追溯到 git 提交（artifact_commit）；报告不入仓导致该字段对报告恒为空；
- Gitea 是 shadow 库默认托管地（ADR-0022 底座分工：GitHub 管代码、Gitea 管影子知识）。

## 决策

1. **持久产物统一进 shadow project**：报告（reports/<task_type>/）、蒸馏卡片（know-how/）、结构化文档（docs/）均写入工程 shadow 仓并 git 提交；`artifact_commit` 为该次提交 SHA（Run 档案 C 段闭环）。
2. **运行态产物不进仓**：Run 日志/prompt/临时文件留在 `data/private/chronicler/runs/`。
3. **默认托管 Gitea**：工程未指定 shadow_repo 时，调 Gitea API 幂等建仓 `<工程名>-shadow` 并推送；无 Gitea（组件未部署/未启用）时纯本地仓，Run 记 `pushed=false` warning。
4. **推送失败不判死**：本地提交成功即 Run 成功（网络抖动不该判死分析任务），推送状态入档案。
5. 报告散区 `data/public/reports/` 废除；mkdocs 挂载改指 `data/public/shadow/`（直接渲染 shadow 仓内容）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 报告留纯文件区，只卡片进仓 | 现状分裂正是要修的；报告无版本无法回溯演化 |
| 持久产物直接提交回原工程仓库 | 污染代码仓历史；AI 产物与代码分离是既定边界（BR-007） |
| 推送失败判 Run 失败 | 网络抖动杀死分析任务不合理；本地 git 已是完整档案 |
| shadow 仓放 private | mkdocs/outline 等读者组件无法挂载消费；产物本就给人看，非机密 |

## 后果

- 正面：产物全部可版本回溯（FR-MGR-013 验收完整达成）；读者组件零对接成本；Run 档案 C 段闭环。
- 负面：shadow 仓体积随时间增长（文本，可忽略）；Gitea 建仓失败时降级为本地仓需要运维感知。
- 同步：what/manager.md §2.1.1、requirements FR-MGR-013、traceability、AGENTS.md；mkdocs 挂载换源。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
