# ADR-0013 系统数据优先 Git 管理（历史完整、可审查、可追溯）

> 日期：2026-08-26 · 状态：已接受
> 关联：what/environment.md、what/knowledge.md、what/req-mgmt.md、what/manager.md；需求 NFR-009、FR-KB-001、FR-REQ-001、FR-CI-004；ADR-0006

## 背景

用户原则：**系统的数据尽量使用 Git 管理，好处是历史完整、可审查、可追溯**。决策时刻已有的一致先例：文档即代码（why/principles.md #12）、知识 vault 是 Git 仓库（FR-KB-001）、需求即代码（FR-REQ-001，ADR-0006）、Jenkins 配置即代码（FR-CI-004）。同时存在明确边界：DB 型服务（OpenProject、Outline、Manager 的 Postgres）与二进制数据（向量索引、镜像、构建产物）无法直接 Git 化。

## 决策

凡可文本化的系统数据——配置、文档、需求、Prompt 库、报告、知识、任务/运行元数据——一律以 **Git 仓库为事实源**；数据库与二进制存储只作运行时层/索引层，必须可重建或可导出回 Git，不得成为唯一副本。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 全部数据入 DB（OpenProject 模式推广到一切） | 历史不可审查、diff 不可读，直接违背可追溯目标 |
| DB 为事实源 + 定时导出到 Git | 事实源仍在 DB，导出滞后且双向同步复杂；降级为 DB 型服务的补偿手段而非主策略 |
| Git 事件溯源（一切运行时操作经 Git 提交） | 运行时性能与复杂度不可接受，GUI 服务（OpenProject/Outline）无法适配 |

## 后果

- 正面：历史完整、可 diff、可审计；备份 = `git clone/pull`；与既有"文档即代码"路线完全一致；Agent 可直接读取事实源（与 FR-REQ-001 同构）。
- 负面：DB 型服务（OpenProject、Outline、Manager 库）只能靠"导出/同步进 Git"补偿，存在滞后；Manager 的 prompt 库、报告、任务元数据需设计 Git 落盘机制（M3 起落地），不能简单只写 Postgres。
- 同步：why/principles.md 新增原则 #15；NFR-009 与 traceability.md 已登记；Manager 数据模型落地时以 Git 为事实源（what/manager.md 随 M3 更新）；OpenProject/Outline 侧以定期导出补偿（具体机制随任务管理落地再定，见 ADR-0011）。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
