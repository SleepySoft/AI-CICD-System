# 功能需求：Manager 管理服务（MGR）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：Manager 的功能需求；规格（数据模型/API/权限）见 `../../what/manager.md`，机制见 `../../how/manager-architecture.md`

### FR-MGR-001 工具总览面板
- 状态: 生效 | 上层: UR-006 | 优先级: P0
- 描述: 集中展示环境内所有工具（分组卡片、运行状态实时探测、跳转链接）；boss 可启停/重启容器。
- 验收: 打开面板可见 tools.yaml 中注册的全部工具及其实时状态。

### FR-MGR-002 Agent 终端
- 状态: 生效 | 上层: UR-007 | 优先级: P0
- 描述: 基于 terminal-runtime（ATR）的会话控制台：创建任意 CLI 会话、查看屏幕、提交命令与按键；boss 可操作，dev 只读。
- 验收: boss 可创建并操作 kimi/aider/bash 会话；dev 登录仅可观察。

### FR-MGR-003 代码源管理
- 状态: 生效 | 上层: BR-002 | 优先级: P0
- 描述: 注册任意 git 远端（Gitea/GitHub）代码源，支持凭据引用、定时同步、查看同步日志。
- 验收: 添加代码源后可同步到本地缓存卷，`last_commit` 可见。

### FR-MGR-004 任务定义与多方式触发
- 状态: 生效 | 上层: BR-002 | 优先级: P0
- 描述: 任务 = 代码源 + Agent 配置 + Prompt 模板 + 调度；支持 cron 定时、手动触发、Gitea Webhook 触发。
- 验收: 三种触发方式均产生 task_run 且 `trigger` 字段正确。

### FR-MGR-005 一切皆 Run
- 状态: 生效 | 上层: BR-002 | 优先级: P0
- 描述: 每次执行产生含输入快照（commit 范围、prompt 版本、CI 上下文）的 Run，可回溯、可重放、可重跑。
- 验收: 任一历史 Run 可查看输入快照与日志，并可基于快照重跑。

### FR-MGR-006 实时日志
- 状态: 生效 | 上层: UR-004 | 优先级: P1
- 描述: 运行中的任务经 SSE 流式输出日志。
- 验收: 任务运行期间前端日志实时滚动，无需刷新。

### FR-MGR-007 内置六类分析任务
- 状态: 生效 | 上层: BR-002, BR-003, BR-004, BR-006 | 优先级: P1
- 描述: 内置 code-insight / daily-report / deviation-analysis / compliance-check / knowhow-distill / comprehensive-report，另支持 custom 任务。
- 验收: 每类任务以默认模板开箱可跑，产出进入报告中心或待审区。

### FR-MGR-008 报告中心与分级可见
- 状态: 生效 | 上层: UR-004, BR-008 | 优先级: P1
- 描述: 报告按类型/仓库/时间过滤，Markdown 渲染；`visibility` 控制 dev/boss 可见性，API 层强制过滤。
- 验收: boss 级报告对 dev 账号在 API 与页面均不可见。

### FR-MGR-009 待审闭环
- 状态: 生效 | 上层: UR-005, BR-007 | 优先级: P1
- 描述: AI 产出（know-how 卡片、文档草稿等）先落待审区，批准后转正入库并重建索引，驳回归档。
- 验收: 批准的知识卡片进入 `know-how/` 且可被语义检索；审批与驳回有审计记录。

### FR-MGR-010 CI 结果消费
- 状态: 生效 | 上层: BR-004 | 优先级: P1
- 描述: 经 Jenkins REST 拉取构建结果写入 Run 的 `ci_context`；综合报告按时间窗聚合 CI 结果；只读为主，不反向操控流水线。
- 验收: 综合报告中包含同期 Jenkins 构建号与结果。

### FR-MGR-011 Prompt 库版本化
- 状态: 生效 | 上层: BR-009 | 优先级: P1
- 描述: Prompt 模板入库、版本化，内置模板只读可复制为自定义；任务记录所用版本。
- 验收: 修改模板后历史 Run 仍关联其执行时的版本。
