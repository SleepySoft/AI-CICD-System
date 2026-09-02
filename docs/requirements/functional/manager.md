# 功能需求：Manager 管理服务（MGR）

> 版本：v1.6 · 日期：2026-09-02 · 状态：生效
> 定位：Manager（supervisor/Chronicler，ADR-0020/0022）的功能需求；规格（数据模型/API/权限）见 `../../what/manager.md`，机制见 `../../how/manager-architecture.md`

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
- 描述: 每次执行（无论触发方式、无论成败）产生完整 Run 档案：输入快照（分析基于的提交、prompt 版本与渲染全文、harness 命令与版本、注入资源清单、触发人）+ 执行过程（状态机、日志、错误归类）+ 产物清单（生成/更新了哪些产物、产物落入的 git 提交）。字段明细与规约见 `../../what/manager.md` §2.1.1。
- 验收: 任一历史 Run（含失败的）可查看输入快照、本次实际使用的 prompt 全文、日志与产物清单；产物为 git 内容时可定位到具体提交；进程中断/supervisor 重启导致的悬挂状态（queued/running 超时未落库）由调度器自动检测并标记失败（error_class=悬挂）。

### FR-MGR-006 实时日志
- 状态: 生效 | 上层: UR-004 | 优先级: P1
- 描述: 运行中的任务经 SSE 流式输出日志。
- 验收: 任务运行期间前端日志实时滚动，无需刷新。

### FR-MGR-007 内置任务与 Prompt 家族
- 状态: 生效 | 上层: BR-002, BR-003, BR-004, BR-006 | 优先级: P1
- 描述: 内置 project-analysis / documentation-update / daily-report / comprehensive-report / knowledge-capture 五类任务，复用 project-analysis / documentation-update / periodic-report / knowledge-capture 四个 Prompt 家族；任务类型通过 registry 绑定 Prompt 与模式，另支持 custom 任务。
- 验收: 五类任务均可从任务列表选择并以默认模板运行；日报与综合报告使用同一 Prompt 的不同模式；Prompt 库只展示四个家族；历史任务类型可映射到新家族继续运行。

### FR-MGR-008 报告中心与分级可见
- 状态: 生效 | 上层: UR-004, BR-008 | 优先级: P1
- 描述: 报告按类型/仓库/时间过滤，Markdown 渲染；`visibility` 控制 dev/boss 可见性，API 层强制过滤。
- 验收: boss 级报告对 dev 账号在 API 与页面均不可见。

### FR-MGR-009 待审闭环
- 状态: 生效 | 上层: UR-005, BR-007 | 优先级: P1
- 描述: 采用审核发布策略的 AI 产出（know-how 卡片、文档草稿等）以 Git 变更进入待审区，批准后合并转正并重建索引，驳回则关闭但保留 Run 与提交记录。
- 验收: 待审项可查看来源 Run、提交、变更文件与 diff；批准后变更进入目标默认分支，批准、驳回和合并均有审计记录。

### FR-MGR-010 CI 结果消费
- 状态: 生效 | 上层: BR-004 | 优先级: P1
- 描述: 经 Jenkins REST 拉取构建结果写入 Run 的 `ci_context`；综合报告按时间窗聚合 CI 结果；只读为主，不反向操控流水线。
- 验收: 综合报告中包含同期 Jenkins 构建号与结果。

### FR-MGR-011 Prompt 库版本化
- 状态: 生效 | 上层: BR-009 | 优先级: P1
- 描述: Prompt 模板入库、版本化，内置模板只读可复制为自定义；任务记录所用版本。
- 验收: 修改模板后历史 Run 仍关联其执行时的版本。

### FR-MGR-012 项目全景仪表盘
- 状态: 生效 | 上层: UR-004 | 优先级: P2
- 描述: 仪表盘聚合各代码源活跃度（最近 commit/变更摘要）、运行中与近期任务、待审与偏离告警计数。
- 验收: 打开 `/` 可见各注册代码源的最近提交与任务状态汇总，无需逐页进入。

### FR-MGR-013 项目影子库（project_shadow）
- 状态: 生效 | 上层: BR-007 | 优先级: P1
- 描述: 每个受管项目一个 shadow git 仓（`data/public/shadow/<工程名>-shadow`，ADR-0028）：承载分析报告（reports/）与蒸馏卡片（know-how/）等全部持久产物，统一 git 提交并推送远端（默认 Gitea 自动建仓，可指定任意 git 远端）；内容本体在 git，Chronicler 仅存索引（NFR-009）。
- 验收: Run 的 artifacts 含 shadow 提交 SHA 与推送状态；Gitea 仓可见对应提交；未配置远端时纯本地仓也成立。

### FR-MGR-014 全局资产库
- 状态: 生效 | 上层: BR-007 | 优先级: P1
- 描述: 一个全局 git 仓库承载跨项目可复用的经验与组件；已在项目内确认的条目复制为全局候选，经独立人工审核与合并后上升，保留来源项目、Run 与提交引用。
- 验收: 项目条目可产生全局库待审变更，批准合并后可从全局默认分支读取；未经第二次审核不得进入全局默认分支；全局库可独立 clone 使用。

### FR-MGR-015 资源能力注入（skill 化）
- 状态: 生效 | 上层: UR-007 | 优先级: P0
- 描述: 内外部资源（OpenProject、JIRA、Qdrant、shadow/全局资产库等）以能力描述注册：访问途径（文件路径/API）+ 凭据引用 + 用途说明；任务 prompt 组装时只注入已配置资源的访问说明，agent 自主决定是否及如何使用；未配置的资源不出现在 prompt 中。
- 验收: 配置某资源后，Run 的 prompt 快照含其访问说明且 agent 可据此实际访问；移除配置后不再出现。

### FR-MGR-016 任务来源适配与降级
- 状态: 生效 | 上层: BR-002, BR-003 | 优先级: P1
- 描述: 任务来源多层组合并可降级：OpenProject 工作包（已配置时取下一个 task 并核对偏差）→ 文本文件提交 → 直接指令；无 OpenProject 时 agent 依据项目上下文（AGENTS.md + git 提交历史）自主规划。
- 验收: 三种来源均可产生任务与 Run；未配置 OpenProject 时其余功能不受影响。

### FR-MGR-017 分角色鉴权与可插拔鉴权后端
- 状态: 生效 | 上层: UR-006, BR-008 | 优先级: P0
- 描述: supervisor 本体提供分角色鉴权，至少 admin（管理）/ user（普通）两级：配置、工程管理、任务触发等写操作仅 admin；鉴权后端可插拔（Keycloak OIDC 或本地账密），无 Keycloak 底座时可独立运行。
- 验收: user 角色调用 admin 接口被拒（403）；两种鉴权后端下登录与权限判定均可用。

### FR-MGR-018 全局组件配置
- 状态: 生效 | 上层: UR-009 | 优先级: P0
- 描述: 全局配置登记本地启用哪些组件适配器（git 托管/CI/任务管理/知识库等）及其参数；未启用的组件不出现在任务可用资源与 prompt 注入中（配套 FR-MGR-015），对应功能自动降级而非报错。
- 验收: 停用某组件后，新建 Run 的 prompt 快照不含该组件访问说明，依赖它的任务来源按 FR-MGR-016 降级。

### FR-MGR-019 Agent harness 登记（命令模板）
- 状态: 生效 | 上层: UR-007, UR-009 | 优先级: P0
- 描述: 按 ADR-0021，agent 注册表只登记 harness 条目：名称 → 可执行命令 + 参数模板（含 yolo 类开关）+ 会话能力声明（持久/一次性）；命令形式可配置——prompt 经 `{prompt_file}` 文件或 stdin 管道传入，报告经 `{report_file}` 文件或 stdout 捕获产出，工作目录可选工程仓库/shadow 库，且可由任务定义覆盖（解析顺序：任务覆盖 > harness 默认 > 工程仓库）；admin 可在配置页新增/编辑/删除 harness（写入 DATA 覆盖副本，内置文件只读）；全局默认 harness 可在配置页选择，工程级未覆盖时生效（FR-MGR-020）。supervisor 不接管安装与版本锁定，安装脚本仅为可选沙箱（terminal-runtime）保留。
- 验收: 登记一个本机已装 harness 后可被任务调用产生 Run；配置页增删改 harness 热生效；设置全局默认 harness 后，未设置覆盖项的工程 Run 使用该默认值；任务定义设置工作目录后其 Run 在对应目录执行、未设置时回落 harness 默认与工程仓库；注册表不含安装脚本与密钥明文（env 值只回显键名）。

### FR-MGR-020 工程实体与配置覆盖
- 状态: 生效 | 上层: UR-009, BR-002 | 优先级: P1
- 描述: 工程为一等实体：核心是一个 git 链接（任意远端），复杂项目可附加 CI/CD 项目链接（关联 FR-MGR-010 的构建消费）；工程可覆盖全局配置——agent harness、prompt 方案、分析策略，未覆盖项回落全局默认；任务定义可在工程覆盖之上再指定 harness 与工作目录（解析顺序：任务级 > 工程级 > 全局默认）。
- 验收: 工程设置覆盖项后其 Run 使用工程值，其余工程不受影响；未设置覆盖项的 Run 使用全局默认；任务定义设置 harness/工作目录后，该任务 Run 优先使用任务值。

### FR-MGR-021 工程分析策略配置
- 状态: 生效 | 上层: UR-009, BR-002, BR-007 | 优先级: P1
- 描述: 每个工程的分析策略可配置：任务种类 ↔ prompt 模板 ↔ 产出重构方式（报告/文档组织/shadow 仓库写入位置 FR-MGR-013）的映射、文档组织模板、shadow 仓库组织约定；全局提供默认策略，工程级可覆盖（FR-MGR-020）。
- 验收: 两类任务种类产出按各自配置落入对应位置（报告中心/文档目录/shadow 仓库路径）；Run 输入快照记录所用策略版本。

### FR-MGR-022 组件生命周期管理（自启/日志/详情/插件化注册）
- 状态: 生效 | 上层: UR-006, UR-009 | 优先级: P1
- 描述: 组件目录自包含（components/<name>/ 一个目录装一切：plugin.yaml 注册 + 可选 SKILL.md 能力 + 可选 hooks/backup.py、deploy.py，ADR-0027）；supervisor 只做目录扫描与契约调用，不含组件特定信息。每个组件可标记自启——supervisor 启动时自动拉起（停止的 docker start，容器不存在则组件 deploy 钩子或 `docker compose -f <组件 compose.yml> up -d` 现场创建）与关键组件（critical，关自启/停止需强确认）；登录用户可查看组件日志与运行详情；admin 可一键部署未部署组件（实时进度）。
- 验收: 新增组件 = 建一个目录即注册成功；容器全部停止/删除后仅启动 supervisor，标记自启的组件全部自动恢复；critical 组件操作有确认提示；日志/详情/部署进度接口可用。

### FR-MGR-023 组件自检（契约校验 + 隔离沙箱部署测试）
- 状态: 生效 | 上层: UR-009, BR-002 | 优先级: P1
- 描述: 每个组件可自动自检：plugin.yaml/SKILL.md/备份钩子契约校验；可选隔离部署测试——以独立 compose 项目名与临时数据目录拉起组件，零配置/默认配置验证可达 healthy 后销毁，不影响正式实例。组件可提供 hooks/test.py 自测钩子优先于通用测试。
- 验收: `python -m chronicler test` 全部组件契约通过；`--deploy` 沙箱测试后正式实例运行状态不变且无沙箱残留。

### FR-MGR-024 人机 Web 终端（Human Terminal）
- 状态: 生效 | 上层: UR-010, UR-009 | 优先级: P1
- 描述: 用户在浏览器获得经 Chronicler 后端中转的交互式终端（xterm.js + WebSocket），进入受管工程工作区，支持上下文注入（prompt/skill，复用 injectable_components）与手动启动 agent（vibe coding）。浏览器↔后端仅 HTTP(S)/WebSocket，任何链路不得要求用户在浏览器侧发起 SSH（公司网络拦截 SSH 出口，ADR-0030）。P0 以 SSHwifty 组件提供能力，P1 内置。
- 验收: 打开工程终端即进入该工程工作区目录；会话横幅含注入的 prompt/skill 清单；会话有鉴权与审计；浏览器侧无任何 SSH。

### FR-MGR-025 手动会话上下文注入（约定文件 + 动态 SKILL + chai）
- 状态: 生效 | 上层: UR-010, UR-009 | 优先级: P1
- 描述: 手动 agent 会话（Web 终端或 chai 本地入口）进入工程工作区时，注入与自动 Run 同源（injectable_components）的上下文：工作区根生成/刷新 AGENTS.md 与 CLAUDE.md（@AGENTS.md 桥接），并按 harness 在 .codex/skills、.kimi/skills、.claude/skills 下生成 chronicler 瘦 SKILL；chai 统一 cd/刷新/设 env/拉起 CLI；不写用户级 skills 目录（ADR-0032）。
- 验收: 在受管工程内分别以 kimi/codex/claude 启动，三家均能按各自机制读到 chronicler 能力与组件 SKILL 路径；会话横幅列出注入清单；移除注入文件后三家会话不再出现该上下文。

### FR-MGR-026 AI 产物 Git 发布策略
- 状态: 生效 | 上层: UR-005, UR-009, BR-007 | 优先级: P1
- 描述: Chronicler 统一负责 AI 产物的 Git 提交与发布，工程可按产物类型配置 `review`（任务分支 + Pull Request）、`direct`（直接提交默认分支）或 `local`（仅本地提交）策略；项目经验提升为全局资产固定使用 `review`。
- 验收: `review` 产生关联 Run 的任务分支、提交和可访问 PR；`direct` 在远端基线未变化时更新默认分支且不创建 PR；`local` 不推送；Run 可查看发布策略、分支、提交、PR URL 与独立发布状态；harness 无需持有仓库推送或 Gitea API 凭据。
