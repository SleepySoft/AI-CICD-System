# Prompt 上下文构建与渲染

> 版本：v1.0 · 日期：2026-09-21 · 状态：生效
> 定位：解释标准 Prompt 上下文在 Runner 中的构建、来源、渲染和兼容机制。
> 关联需求：FR-MGR-031；关联决策：[ADR-0049](../adr/0049-standard-prompt-context.md)；字段契约：[what/prompt-context.md](../what/prompt-context.md)

## 1. WHY

Prompt 需要一份完整的运行事实，而不是由每个调用点临时拼变量。统一构建可以避免缺字段静默启动、同名字段异义，以及 Git、Shadow、增量、Harness 和输出路径事实分散在不同模块中。

## 2. HOW

Runner 在分配 `run_id` 并准备 Run 目录后调用：

1. `change_detection.capture()` 采集基线到当前状态的 `change_summary`。
2. `chronicler.app.prompt_context.build_prompt_context()` 读取工程、源仓、Shadow、Run 基线、Harness、组件和 CI 事实。
3. `change_detection.format_context()` 的结果作为人类可读 `change_context`。
4. `chronicler.app.prompt_context.render_prompt()` 用标准字段严格替换 Prompt 正文，拒绝未知字段和未填充占位符。

## 3. 字段来源

| 分组 | 来源 |
|---|---|
| Run / Prompt | `task_runs`、Prompt Catalog 和 Prompt YAML 元数据 |
| 工程 | `projects.get_project()` |
| 源仓 | `projects.current_branch()`、`projects.head_commit()`、`projects.repo_dirty()` |
| Shadow 仓 | `projects.ensure_shadow_repo()`、`projects.shadow_head()`、`projects.shadow_dirty()` |
| Shadow 状态 | Shadow 仓中的 `.cognitive-state.yaml` |
| Run 基线 | 上次成功 Run 的 `baseline_run_id` 和 `change_summary.base_revision` |
| 增量 | `change_summary_json` 和 `change_context` |
| Harness | Harness Registry 配置和 Runner 的 `_report_delivery()` |
| 组件 | `registry.injectable_components()` |
| CI | Runner 的 `_ci_context()` |

Shadow 状态映射如下：

- `source.commit` 映射为 `shadow_source_baseline_commit`。
- `maintenance.last_run` 映射为 `shadow_last_run_file`。
- 状态文件读取失败映射为 `shadow_state_error`；其余缺失事实统一为空字符串。

## 4. 兼容策略

新增字段必须先扩展 WHAT 契约和 `prompt_context.py` 中的 `CONTEXT_FIELDS`，再修改 Prompt；Prompt YAML 的 `variables` 只声明正文实际使用的字段。旧别名不保留兼容层，发现即迁移为标准字段。
