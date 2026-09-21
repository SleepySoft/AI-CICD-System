# Prompt 注入上下文契约

> 版本：v1.0 · 日期：2026-09-21 · 状态：生效
> 定位：定义所有任务 Prompt 可使用的标准运行上下文字段与编写规则；不定义具体业务任务、调度周期和 Agent 输出格式。
> 关联需求：FR-MGR-031

## 1. WHY

Prompt 需要稳定的运行事实，而不是由每个任务自行发明变量名。统一上下文可以避免 `repo_head`、`target_commit`、`date`、`report_mode` 等名称在不同任务里表达不同含义。设计理由见 [ADR-0049](../adr/0049-standard-prompt-context.md)。实现机制见 [how/prompt-context.md](../how/prompt-context.md)。

## 2. WHAT

### 2.1 命名规则

| 前缀或后缀 | 含义 |
|---|---|
| `run_` | 一次 Run 的身份、时间、输出路径 |
| `task_` | 任务定义或任务类型信息 |
| `project_` | Chronicler 中的工程标识 |
| `source_` | 被分析的源代码仓 |
| `shadow_` | Cognitive Shadow 仓 |
| `baseline_` | 同任务上次成功 Run 形成的基线 |
| `change_` | 基线到当前状态的有效输入变化 |
| `harness_` | Agent 执行器和交付方式 |
| `_json` | 机器可读 JSON 字符串 |
| `_context` | 面向 Prompt 的人类可读摘要 |

`baseline_source_commit` 是同任务上次成功 Run 覆盖到的源仓提交；`shadow_source_baseline_commit` 是 Shadow 仓声明的最后一次成功维护的源仓提交。二者可能不同，禁止混用。

### 2.2 标准字段

| 分组 | 字段 | 语义 |
|---|---|---|
| 契约 | `context_schema_version` | 本上下文契约版本，当前为 `1` |
| Run | `run_id`、`task_id`、`task_type`、`task_mode`、`trigger_kind`、`run_actor` | 本次执行身份；`task_id` 可为空 |
| Run 时间 | `run_date`、`run_started_at`、`run_timezone` | 本地执行日期、ISO 8601 启动时间和时区 |
| 工程 | `project_id`、`project_name` | Chronicler 工程标识 |
| 源仓 | `source_repo_dir`、`source_repo_url`、`source_default_branch`、`source_branch`、`source_head_commit`、`source_dirty` | 源仓路径、远端、分支、HEAD 和脏状态 |
| 源仓同步 | `source_synced_at`、`source_sync_error` | 最近同步时间和错误；无数据时为空 |
| Run 基线 | `baseline_run_id`、`baseline_source_commit`、`baseline_run_finished_at`、`baseline_record_file` | 同任务上次成功 Run 的身份、提交、完成时间和报告路径 |
| 增量 | `change_policy`、`change_state`、`change_summary_json`、`change_context` | 增量策略、状态、结构化统计和人类可读摘要 |
| Shadow 仓 | `shadow_repo_dir`、`shadow_repo_url`、`shadow_head_commit`、`shadow_dirty` | Shadow 仓路径、远端、HEAD 和脏状态 |
| Shadow 状态 | `shadow_source_baseline_commit`、`shadow_last_run_file`、`shadow_state_error` | Shadow 声明的源仓基线、上次运行记录和状态文件错误 |
| 执行 | `harness_name`、`harness_report_mode`、`harness_cwd`、`harness_timeout_sec`、`report_delivery` | 执行器、输出捕获方式和交付指令 |
| Run 文件 | `run_dir`、`report_file`、`prompt_file`、`log_file` | 本次 Run 的输出路径 |
| Prompt | `prompt_name`、`prompt_version`、`prompt_hash` | Prompt 身份和版本 |
| 能力 | `components`、`components_json`、`ci_url`、`ci_context_json` | 可用组件和外部 CI 上下文 |
| 附加输入 | `extra` | 调用方自然语言补充指令 |
| 周期 | `task_period_start`、`task_period_end`、`task_period_timezone` | 可选时间窗；非周期任务为空 |

时间字段使用 ISO 8601；没有数据时使用空字符串，不使用 `unknown`、`null` 或占位文本。提交字段使用完整 SHA，不使用日期、分支名或短 SHA 替代。

### 2.3 Prompt 编写规则

1. Prompt YAML 的 `variables` 只能声明正文实际使用的标准字段；不要声明备用字段。
2. 优先使用 `source_head_commit`，不要使用 `target_commit`、`head_commit`、`repo_head` 等别名。
3. 同任务增量分析使用 `baseline_source_commit` 到 `source_head_commit`。
4. Shadow 维护使用 `shadow_source_baseline_commit` 到 `source_head_commit` 作为正式认知基线；`baseline_source_commit` 只能作为 Run 基线参考。
5. 周期报告的时间窗使用 `task_period_start` 到 `task_period_end`，并用 `task_period_timezone` 解释时区。
6. 人类可读结论优先使用 `change_context`；程序可读统计使用 `change_summary_json`。
7. `components` 用于人工阅读，`components_json` 用于机器读取；Prompt 正文必须说明组件只是能力入口，不代表数据存在或任务成功。
8. `report_delivery` 是输出方式契约，不要与 `harness_report_mode` 混用；后者只表示 `file|stdout`。
9. 不要把日期解释为基线，不要把脏工作区当作已提交事实，不要把无数据解释为成功。
10. 缺失、无权限、调用失败和查询无数据必须在正文中要求 Agent 分开陈述。

AI 编写新 Prompt 时，必须先读取本文件；字段名只能取自 §2.2，不能为单个 Prompt 私自新增变量。若现有字段确实不足，应先扩展本文档和上下文契约版本，再修改 Prompt。

## 3. HOW

实现机制、数据来源和兼容策略见 [how/prompt-context.md](../how/prompt-context.md)。Prompt Catalog 只校验 Prompt 正文声明了哪些字段，运行时可以构造完整标准上下文。
