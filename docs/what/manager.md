# Manager 规格（数据模型 / API / 任务框架 / 权限 / 页面）

> 版本：v1.2 · 日期：2026-08-27 · 状态：生效
> 定位：Manager 对外可见的契约与规格；内部机制（架构、执行管线、CI 集成）见 ../how/manager-architecture.md
> 关联需求：FR-MGR-001 ~ FR-MGR-011、FR-TASK-002、FR-TASK-003、BR-008

## 1. WHY

Manager 是环境之上的"管理程序"：配置代码源、配置 Agent、编排定时/触发式分析任务、产出报告与文档、鉴权展示。与 CI/CD 不冲突（Non-Goal 见 ../why/vision.md）。

## 2. WHAT

### 2.1 核心数据模型（Postgres，库 `manager`）

```
repo_source        代码源：name, url(任意 git 远端，含 GitHub/Gitea), auth(ssh key/token 引用),
                   default_branch, sync_cron, last_synced_at, last_commit,
                   shadow_repo(project_shadow 影子库 URL，FR-MGR-013)
agent_profile      Agent harness 配置：name, command(可执行命令 + 参数模板，如 --yolo),
                   session_cap(persistent|oneshot|resume，会话能力声明), model, base_url,
                   api_key_ref(密钥存加密列或挂载 secret), max_runtime_sec
prompt_template    Prompt 库：name, scope(system|task), content(支持 {{变量}}), version,
                   builtin(bool), updated_by, updated_at
task_def           任务定义：name, type(见 §2.3), repo_ids[], agent_id, prompt_id,
                   schedule_cron, enabled, params(JSON), output_visibility(dev|boss)
task_run           一次执行：task_id, status(queued|running|success|failed|canceled),
                   trigger(cron|manual|webhook), started_at, finished_at, input_snapshot(JSON),
                   runner_container, log_path, error, ci_context(JSON, 关联的 Jenkins 构建),
                   openproject_id(关联的 OpenProject 工作包，可空，FR-TASK-002/003)
report             报告：run_id, title, type, visibility, md_path, summary, created_at,
                   reviewed(bool), reviewer
review_item        待审区条目：run_id, kind(knowhow|doc|common-module|...),
                   payload(JSON/diff), status(pending|approved|rejected), decided_by
asset              可复用资产索引：scope(project|global), kind(experience|component),
                   source_run_id, git_repo, git_path, status(pending|approved|promoted),
                   title, summary, created_at —— 内容本体在 git（NFR-009），DB 仅存索引
audit_log          审计：actor, action, target, detail, at
```

契约要点：

- **prompt_template 版本化**（FR-MGR-011）：任务记录 prompt 版本，Run 可复现。
- **密钥不落明文**（NFR-002）：`api_key_ref` 指向 Docker secret 或加密列（Fernet，密钥来自 .env）。
- **CI 上下文入 Run**（FR-MGR-010）：`ci_context` 记录同期 Jenkins 构建号/结果。
- **Agent 用户自装 harness**（ADR-0021，部分推翻 ADR-0017）：CLI 由用户在 supervisor 所在宿主自行安装与登录，supervisor 只登记命令模板（`command` + 参数），不接管安装与版本锁定；会话经 ATR 抽象尽力持久（harness 不支持持久会话则一次性 + resume 续接，语义 TBD）；terminal-runtime 保留为可选隔离沙箱（CI/不可信任务）。endpoint 抽象（`base_url` + key）与登录态复用约定沿用 ADR-0017 未推翻部分。
- **Agent 注册表过渡形态**（ADR-0018，契约已随 ADR-0021 更新）：当前以 `manager/agents.yaml`（只读挂载热更新）为 agent 清单单一事实源，字段与本表 `agent_profile` 同名，M2 建库后原样迁移；`scripts/agents/<name>.sh` 锁版本安装脚本降级为 terminal-runtime 沙箱专用；操作流程见 ../runbooks/agent-onboarding.md。
- **git 是唯一硬依赖**（ADR-0022）：代码源必须是 git 仓库，托管位置不限；其余组件（OP/JIRA/Qdrant/SSO 等）均可选、可替换、可外部。
- **资源能力经 skill 注入**（FR-MGR-015）：资源以能力描述（访问途径 + 凭据引用 + 用途说明）注册，prompt 只携带已配置资源的访问途径，agent 自主翻看；未配置的资源不出现在 prompt 中，系统按此降级。
- **资产两级沉淀**（FR-MGR-013/014）：项目经验与代码抽取先入 `project_shadow`（每项目一个 git 仓库），经审批上升到全局资产库；内容本体在 git，Chronicler 只存索引（`asset` 表）。

### 2.2 API 概要

```
POST   /api/auth/callback            OIDC 回调
GET    /api/me                       当前用户与角色
CRUD   /api/repos                    + POST /api/repos/{id}/sync
CRUD   /api/agents                   + POST /api/agents/{id}/test（连通性自检）
                                   （过渡落地 ADR-0018：GET /api/agents 已实现，CRUD/test 待 M2；
                                     ADR-0021 后 install 接口废弃——agent 用户自装，不再由 Manager 安装）
CRUD   /api/prompts                  + GET /api/prompts/{id}/versions
CRUD   /api/tasks                    + POST /api/tasks/{id}/trigger | /toggle
GET    /api/runs?task_id=&status=    + GET /api/runs/{id} | /logs(SSE) | /rerun
GET    /api/reports?type=&visibility= + GET /api/reports/{id}（渲染）| /export
GET    /api/review                   + POST /api/review/{id}/approve | /reject
GET    /api/assets?scope=&kind=      + POST /api/assets/{id}/promote（shadow → 全局库，FR-MGR-014）
POST   /api/webhooks/gitea           push 触发
GET    /api/health                   供 Uptime Kuma
```

### 2.3 任务类型框架（TaskType Registry）

每类任务注册四件套：`collector()`（采集输入）→ `prompt_vars()`（组装变量）→ `output_parser()`（解析产出）→ `persister()`（落库/分发）。

| 内置任务 | 输入 | 产出 |
|---------|------|------|
| `code-insight` | 仓库增量 diff + 既有 WHY/WHAT/HOW 文档 | 结构化文档草稿 → 待审区 → 文档站 |
| `daily-report` | 当日 commits + diff + issue + Jenkins 当日构建结果 | 日报（默认 boss 可见） |
| `deviation-analysis` | 需求/任务（OpenProject 适配器或文本文件，降级见 FR-MGR-016）+ 代码 + 文档 | gap 报告（含严重度）+ 可选自动建 issue |
| `compliance-check` | 文档站 + 脚本目录 + 合规规则模板 | 合规报告（违规清单+整改建议） |
| `knowhow-distill` | commit 区间/目录/会话上下文 | 知识卡片 → 待审 → project_shadow（可再上升全局资产库） |
| `comprehensive-report` | 各报告 + CI 汇总 + 需求进度 | boss 专属综合报告 |

自定义任务：选 repo + agent + prompt + cron 即成新任务（`type=custom`）。

### 2.4 权限规格（FR-MGR-008）

- 角色映射：Keycloak `groups` claim → `boss`（全部可见 + 审批 + 管理配置）/ `dev`（可见 visibility=dev 的内容）/ `admin`（平台配置）。
- 双层过滤：API 层按 `report.visibility` 强制过滤（安全边界）+ 前端路由守卫（体验层）。
- 默认可见性：蒸馏报告、gap 分析、know-how 私库默认 `boss`；日报可选。
- 审计：查看 boss 级报告、审批、配置变更均落 `audit_log`。

### 2.5 前端页面清单

`/login` OIDC 跳转 · `/` 项目全景（各代码源活跃度、任务状态、待审/偏离计数，FR-MGR-012） · `/repos` 代码源 · `/agents` Agent 配置 · `/prompts` Prompt 库 · `/tasks` 任务 · `/runs` 运行记录（SSE 日志） · `/reports` 报告中心 · `/assets` 资产库（shadow/全局库浏览、检索、审批上升，FR-MGR-013/014） · `/review` 待审区 · `/settings` 系统设置（含资源能力注册，FR-MGR-015）

### 2.6 里程碑

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| M1 骨架 ✅ | FastAPI + OIDC + 工具总览 + Agent 终端 + 接入 compose | boss/dev 登录看到不同视图 |
| M2 代码源与执行器 | repo 同步 + harness 执行器（宿主直起）+ 手动触发 + SSE 日志 | 跑一次"总结 README"任务看流式日志 |
| M3 内置任务 | 6 类内置任务 + prompt 库 + 报告中心 | 日报/gap 报告产出，可见性正确 |
| M4 待审闭环 | review 区 + 卡片转正 + shadow/全局资产库 + 文档站更新 | 蒸馏卡片审批后入 project_shadow 并可检索，可上升全局库 |
| M5 CI 综合 | Jenkins 结果接入 + 综合报告 + webhook 触发 | 综合报告含构建结果；push 触发任务 |
| M6 加固 | supervisor Nuitka 打包 + prompt 加密 + 审计 + 限流 | 二进制内无源码与明文 prompt |

## 3. HOW

架构图、执行管线、并发控制、CI 集成机制、部署形态见 ../how/manager-architecture.md。技术选型决策见 ../adr/0007-manager-separate-from-jenkins.md、0008、0009、0010（同目录）。
