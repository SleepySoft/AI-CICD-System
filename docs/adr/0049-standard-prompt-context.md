# ADR-0049 统一 Prompt 运行上下文契约

> 版本：v1.0 · 日期：2026-09-21 · 状态：已接受
> 定位：为 Manager 任务 Prompt 建立唯一的运行上下文字段契约。
> 关联：[ADR-0034](0034-task-prompt-family-registry.md)、[ADR-0035](0035-effective-input-change-detection.md)、[ADR-0036](0036-sealed-runtime-prompt-catalog.md)、FR-MGR-031

## 1. 背景

Manager 的多个 Prompt 家族都依赖工程、源仓、Shadow、增量、Harness 和输出路径事实。此前存在 `repo_head`、`target_commit`、`baseline_commit`、`date`、`report_mode` 等分散变量：同名不同义、同名不同源、缺少数据时仍可能静默启动。随着同任务基线、Cognitive Shadow、组件能力注入和周期任务增多，Prompt 无法继续依赖调用方临时拼装变量。

## 2. 决策

1. 建立唯一的标准运行上下文契约，由 `chronicler/app/prompt_context.py` 构建完整上下文，Runner 统一渲染。
2. 字段使用 `source_`、`shadow_`、`baseline_`、`change_`、`harness_`、`task_period_` 前缀表达事实来源；机器可读数据使用 `_json`，人类可读摘要使用 `_context`。
3. `baseline_source_commit` 表示同任务上次成功 Run 覆盖到的源仓提交；`shadow_source_baseline_commit` 表示 Shadow 声明的认知基线。二者可能不同，禁止混用。
4. 当前源仓 HEAD 统一使用 `source_head_commit`，不再使用 `repo_head`、`target_commit` 或 `head_commit`。
5. 任务模式统一使用 `task_mode`，例如 `daily|comprehensive`；Harness 输出捕获方式统一使用 `harness_report_mode`，交付指令统一使用 `report_delivery`。
6. Prompt YAML 只声明正文实际使用的标准字段，不声明备用字段。
7. `render_prompt()` 严格替换：未知字段或未填充占位符必须渲染失败，不得静默保留 `{{...}}`。

## 3. 备选方案

- **Prompt 自行组装变量**：实现分散，命名漂移无法约束，也容易在缺数据时静默启动。
- **只注入增量摘要**：无法覆盖任务身份、周期、Harness、输出路径和组件能力，需要继续向 Prompt 传临时变量。
- **任意键值上下文**：灵活但不可审计，同一字段会出现多种语义，无法做 Catalog 强校验。

## 4. 后果

运行上下文字段获得单一契约，缺失事实显式为空字符串并在 Prompt 中要求 Agent 分开陈述。新增变量必须先扩展 WHAT 契约和 `CONTEXT_FIELDS`，再修改 Prompt；旧别名继续清除，不保留兼容层。
