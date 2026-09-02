# ADR-0033 AI 产物由 Chronicler 统一 Git 发布与 PR 审核

> 日期：2026-09-02 · 状态：已接受
> 关联：../what/manager.md §2.3.1；需求 FR-MGR-009、FR-MGR-013、FR-MGR-014、FR-MGR-026、BR-007

## 背景

ADR-0028 已决定将报告、结构化文档和经验卡片统一存入 project shadow Git 仓，但现有实现把 Agent 产出直接提交并固定推送到 `main`，无法在发布前方便地查看和审核文档修改。FR-MGR-009 要求 AI 文档与知识可审核，FR-MGR-014 还要求项目经验经确认后再上升到全局资产库。

外部 harness 的职责是分析并生成内容。若让 Kimi、Codex 等 harness 各自执行 Git 提交、push 和创建 PR，会把仓库写凭据暴露给不同工具，并产生不一致的分支名、提交元数据、重试和错误处理。Gitea 1.22 已提供 Pull Request 与相应 REST API，可以直接承载变更审核和合并历史。

同时，不是所有工程都需要 PR：可信的自动文档任务可能希望直接发布，离线工程可能只保留本地提交。项目经验提升为全局经验的影响范围更大，需要保留独立的人工质量门槛。

## 决策

Agent harness 只负责生成约定内容；Chronicler 统一拥有 AI 产物的分支准备、Git 提交、push 和 PR 创建，并按产物类型与工程配置执行以下发布策略：

1. `review`：从冻结基线创建 `chronicler/task-<task_id>/run-<run_id>` 分支，Chronicler 提交并 push，通过 Gitea API 幂等创建 PR，人工查看 diff 后合并或关闭。
2. `direct`：Chronicler 提交后确认远端默认分支仍等于冻结基线，再快进推送；基线变化则报告冲突，禁止 force push。
3. `local`：只保留本地分支与提交，不访问远端。
4. 文档和项目内知识采用工程按产物类型配置的策略；项目经验提升到全局资产库固定使用 `review`，创建全局库的新变更与第二次人工审核，不能继承项目的 `direct` 策略。
5. Run 执行状态与发布状态分离。内容生成成功后，push 或建 PR 失败不改变 Run 的分析结果，发布可基于既有提交独立重试。
6. 同一 shadow 仓的分支准备、Agent 写入、提交和工作树恢复由项目级锁串行化；现有 harness 锁只处理 CLI 自身的共享状态，不能替代仓库锁。
7. 首版审核页展示 Git diff、来源 Run 与 Gitea PR 链接，批准和合并仍由 Gitea 完成；Chronicler 记录 PR 状态。未来可代理 Gitea 合并 API，但不改变 Git 内容的事实源。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Agent 自行 commit、push、创建 PR | 需要向每种 harness 暴露写凭据，提交规范、错误处理和幂等行为不可控 |
| Chronicler 生成自定义 patch 并用数据库实现审核 | 重复 Git 已具备的 diff、分支、冲突与审计能力，增加第二套事实源 |
| 所有产物强制 PR | 对可信自动报告、个人工程和离线场景负担过高 |
| 所有产物直接提交默认分支 | 文档修改不可在发布前审核，无法满足项目经验到全局经验的质量门槛 |
| 项目经验直接跨仓库 merge 到全局库 | 两个仓库历史无共同基线，且缺少归一化、去项目化和第二次审核过程 |

## 后果

正面：Agent 无需仓库写凭据；提交身份、分支名和 Run 关联统一；文档修改可直接利用 Gitea diff/PR；项目到全局的经验提升形成可审计的两级审核；发布失败可独立重试。

负面：Runner 需要增加 shadow 仓锁、发布状态、分支生命周期和 Gitea PR client；长期未处理的任务分支需要清理策略；非 Gitea 远端若要获得同等 PR 体验，需要增加 provider 适配器。

同步更新：../requirements/functional/manager.md、../requirements/traceability.md、../what/manager.md、../how/manager-architecture.md、../README.md。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->