# ADR-0034 任务类型与 Prompt 家族通过 registry 解耦

> 日期：2026-09-02 · 状态：已接受
> 关联：../what/manager.md §2.3；需求 FR-MGR-007、FR-MGR-011、FR-MGR-021

## 背景

初版把一个 Prompt 文件直接等同于一个任务类型，并按分析章节拆出代码洞察、需求偏差、合规检查、日报、综合报告、经验蒸馏和结构化文档。结果是多个模板重复扫描同一仓库，项目分析与文档维护职责重叠，日报和综合报告重复维护，经验任务也容易为满足数量生成泛化内容。代码中的预置任务、需求中的六类任务和实际七个模板已经出现不一致。

FR-MGR-007 需要开箱可用的内置任务，FR-MGR-011 要求模板可独立版本化，FR-MGR-021 要求任务种类、Prompt 和产出策略能够映射。这三者不要求任务类型与模板文件一一对应。

## 决策

采用“5 个执行任务映射到 4 个 Prompt 家族”的 registry：

1. `project-analysis` 使用 `project-analysis/full`，统一承担架构、需求一致性和工程风险诊断，只产出报告。
2. `documentation-update` 使用 `documentation-update/incremental`，按需求、WHY/WHAT/HOW、ADR 与 runbook 边界维护文档。
3. `daily-report` 和 `comprehensive-report` 共享 `periodic-report`，分别使用 `daily` 与 `comprehensive` 模式。
4. `knowledge-capture` 使用 `knowledge-capture/focused`，从具体 Run、提交或故障中提取经验，证据不足时允许零产出。
5. registry 显式记录任务名称、Prompt 名称、模式和描述；Run 冻结实际 `prompt_name` 与 `task_mode`。
6. `code-insight`、`deviation-analysis`、`compliance-check`、`structured-docs`、`knowhow-distill` 保留只读兼容映射，使存量 task_def 可继续执行，但不再预置或出现在新建任务列表。

四个家族共享事实原则：生效需求说明期望，代码/测试/配置说明现状，正式文档和 ADR 说明设计意图，历史报告与 AI 草稿只作为待验证线索。每个家族单独规定允许产物和停止条件，避免 Agent 顺带修改其它内容。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 继续一任务一文件并保留七类 | 职责按报告章节切得过细，重复扫描、维护和结论冲突持续存在 |
| 只保留一个万能分析 Prompt | 输出目标和写入行为差异过大，Agent 容易把分析、文档、报告和知识混在一起 |
| 四个 Prompt 同时只设四个任务 | 日报与综合报告的调度、受众和展示仍是不同任务，强行合并会把模式塞进人工附加指令 |
| 立即删除旧任务类型 | 存量 task_def 和历史 Run 失去可执行语义，迁移风险不必要 |

## 后果

正面：任务职责与模板复用同时成立；日报/综合报告共享质量规则；项目分析与文档维护边界清楚；Prompt 库数量稳定；任务列表可使用面向用户的描述。

负面：配置 API 和前端必须分别处理 task-types 与 prompts；旧类型兼容映射需要在确认无存量任务后另行清理；自定义任务未来需要显式注册 Prompt 和 mode，不能再仅依赖同名文件。

同步更新：../requirements/functional/manager.md、../requirements/traceability.md、../what/manager.md、../how/manager-architecture.md、../README.md、../../AGENTS.md。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->