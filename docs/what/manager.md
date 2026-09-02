# Chronicler（supervisor）规格（数据模型 / API / 任务框架 / 权限 / 页面）

> 版本：v1.4 · 日期：2026-09-02 · 状态：生效
> 定位：Chronicler（原 Manager，宿主侧 supervisor，ADR-0020/0022）对外可见的契约与规格；内部机制（架构、执行管线、CI 集成）见 ../how/manager-architecture.md
> 关联需求：FR-MGR-001 ~ FR-MGR-026、FR-TASK-002、FR-TASK-003、BR-008
> v1 实现注记：存储 SQLite（ADR-0023），鉴权本地账密 admin/user（Keycloak 后端预留），agent 为宿主自装 harness（ADR-0021）；Git 发布已落 direct 基础框架（main 直接提交/推送，不建 PR），远端基线保护及 review/local 仍属规划

## 1. WHY

Manager 是环境之上的"管理程序"：配置代码源、配置 Agent、编排定时/触发式分析任务、产出报告与文档、鉴权展示。与 CI/CD 不冲突（Non-Goal 见 ../why/vision.md）。

## 2. WHAT

### 2.1 核心数据模型（Postgres，库 `manager`）

```
repo_source        代码源：name, url(任意 git 远端，含 GitHub/Gitea), auth(ssh key/token 引用),
                   default_branch, sync_cron, last_synced_at, last_commit,
                   shadow_repo(project_shadow 影子库 URL，FR-MGR-013),
                   publish_policy(JSON：按产物类型配置 review|direct|local，FR-MGR-026)
agent_profile      Agent harness 配置：name, command(可执行命令 + 参数模板，如 --yolo),
                   prompt_form(file|stdin), report_form(file|stdout), cwd(repo|shadow),
                   session_cap(persistent|oneshot|resume，会话能力声明), model, base_url,
                   api_key_ref(密钥存加密列或挂载 secret), max_runtime_sec
prompt_template    Prompt 库：name, scope(system|task), content(支持 {{变量}}), version,
                   builtin(bool), updated_by, updated_at
task_def           任务定义：name, type(见 §2.3), repo_ids[], agent_id, prompt_id,
                   harness(任务级 harness 覆盖，''=回落工程/全局), cwd(repo|shadow|''，
                   工作目录覆盖，''=回落 harness 默认), schedule_cron, enabled,
                   params(JSON), output_visibility(dev|boss)
task_run           一次执行：详细字段见 §2.1.1 Run 档案契约（FR-MGR-005）
report             报告：run_id, title, type, visibility, md_path, summary, created_at,
                   reviewed(bool), reviewer
review_item        待审区条目：run_id, kind(knowhow|doc|common-module|...), git_repo,
                   base_branch, head_branch, commit_sha, pr_number, pr_url,
                   status(pending|approved|rejected|merged|conflict), decided_by
asset              可复用资产索引：scope(project|global), kind(experience|component),
                   source_run_id, git_repo, git_path, status(pending|approved|promoted),
                   title, summary, created_at —— 内容本体在 git（NFR-009），DB 仅存索引
audit_log          审计：actor, action, target, detail, at
```

契约要点：

#### 2.1.1 Run 档案契约（FR-MGR-005，一切皆 Run）

任何一次执行（无论触发方式、无论成败）产生完整档案，分三段记录。标注【v1】= 已实现，其余为规划：

**A. 输入快照（执行前冻结，此后不可变）**

```
run_id             档案 ID                                    【v1】
task_type          任务种类（code-insight/daily-report/…）     【v1】
trigger            manual|cron|webhook                        【v1】（v1 仅 manual）
created_by         触发人（审计追溯）                          【v1】
queued_at          入队时间                                    【v1】
project            工程 id/name/git_url                        【v1】
repo_base_commit   分析基于的提交 SHA（全量，非短 hash）        【v1】
repo_status        工作区是否脏（有未提交改动需警示）        【v1】repo_dirty
harness            name + 解析后的完整启动命令 + CLI 版本      【v1】
prompt             模板版本 hash + 渲染后全文（落库 task_runs.prompt_text，文件副本
                   runs/<id>/prompt.md）                       【v1】
overrides          覆盖来源与工程级覆盖项（harness/prompt/策略；来源：任务>工程>全局）【v1】
components         注入的资源能力清单（SKILL 名 + 版本/hash）   【v1】
extra_prompt       触发时附加指令                              【v1】
ci_context         同期 Jenkins 构建号/结果（FR-MGR-010）
openproject_id     关联的 OpenProject 工作包（FR-TASK-002/003）
```

**B. 执行过程（随状态机流转追加）**

```
status             queued|running|success|failed|canceled     【v1】
started_at / finished_at / duration_sec                        【v1】
runner_env         执行环境：宿主平台、supervisor 版本          【v1】
log_path           完整 stdout/stderr 日志路径                 【v1】
token_usage        prompt/completion token 用量与耗时（harness 能提供时）
error / error_class 失败原因与归类（网络/配额/解析/超时）        【v1】
```

**C. 产物清单（执行后补记——“生成/更新了什么，落在哪个提交”）**

```
artifacts[]        每个产物：kind(report|doc|knowhow|code-snippet)、path、
                   action(created|updated|deleted)、size_bytes
                   【v1】（报告类产物已记；doc/knowhow 类随 M3/M4）
artifact_commit    产物落入 git 的提交 SHA（报告库/shadow 库/目标仓库）
                   【v1】shadow 仓提交 SHA 已回填（ADR-0028）
publication        mode(review|direct|local)、base_commit、branch、push_status、
                   pr_number、pr_url、publish_error（与 Run 执行状态独立）【v1：direct】
review_refs[]      关联的待审区条目（FR-MGR-009）
asset_refs[]       上升入资产库的条目（FR-MGR-013/014）
```

规约：

- **A 段只写一次**：状态流转只允许追加 B/C 段；A 段任何字段不得被后续修改（可复现性的根基）。
- **产物必须落到可引用的提交**：产物是 git 内容时，artifact_commit 必填；文件路径产物至少记 path+action。
- **失败也要有档案**：failed 的 Run 同样冻结 A 段、记录 B 段错误归类，C 段可为空但字段存在。

- **prompt_template 版本化**（FR-MGR-011）：任务记录 prompt 版本，Run 可复现。
- **Run 档案契约**（FR-MGR-005）：输入快照/执行过程/产物清单三段式，见 §2.1.1。
- **密钥不落明文**（NFR-002）：`api_key_ref` 指向 Docker secret 或加密列（Fernet，密钥来自 .env）。
- **CI 上下文入 Run**（FR-MGR-010）：`ci_context` 记录同期 Jenkins 构建号/结果。
- **Agent 用户自装 harness**（ADR-0021，部分推翻 ADR-0017）：CLI 由用户在 supervisor 所在宿主自行安装与登录，supervisor 只登记命令模板（`command` + 参数），不接管安装与版本锁定；会话经 ATR 抽象尽力持久（harness 不支持持久会话则一次性 + resume 续接，语义 TBD）；terminal-runtime 保留为可选隔离沙箱（CI/不可信任务）。endpoint 抽象（`base_url` + key）与登录态复用约定沿用 ADR-0017 未推翻部分。
- **Agent 注册表过渡形态**（ADR-0018，契约已随 ADR-0021 更新）：当前以 `manager/agents.yaml`（只读挂载热更新）为 agent 清单单一事实源，字段与本表 `agent_profile` 同名，M2 建库后原样迁移；`scripts/agents/<name>.sh` 锁版本安装脚本降级为 terminal-runtime 沙箱专用；操作流程见 ../runbooks/agent-onboarding.md。
- **git 是唯一硬依赖**（ADR-0022）：代码源必须是 git 仓库，托管位置不限；其余组件（OP/JIRA/Qdrant/SSO 等）均可选、可替换、可外部。
- **资源能力经 SKILL 渐进披露注入**（FR-MGR-015、ADR-0024/0025）：组件目录的 `SKILL.md` 存在即注入（L0 摘要+路径常驻 prompt，正文 agent 按需自读）；无 SKILL 的组件（输出消费类）不注入。
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

### 2.3.1 Git 发布与审核契约

FR-MGR-009/013/014/026 共用同一个 Git 变更审核模型，完整决策见 ../adr/0033-chronicler-owned-git-publication.md：

当前实现边界：仅开放 `direct`。Chronicler 检查 shadow 工作树干净后切换或规范为 `main`，直接提交并 push `HEAD:main`，不创建任务分支或 PR；Run 已记录独立 publication。下列基线冲突保护及 `review/local` 是目标契约，尚未实现。

- Agent harness 只生成约定内容；分支准备、`git add/commit`、push 与创建 PR 均由 Chronicler 执行，仓库写凭据不注入 harness。
- `review`：从目标默认分支基线创建 `chronicler/task-<task_id>/run-<run_id>`，提交并推送后创建 Gitea PR；页面展示来源 Run、文件列表、diff 与 PR 链接，人工在合并前审核。
- `direct`：不创建 PR；仅当远端默认分支仍等于 Run 基线时推送，基线变化则标记冲突，禁止 force push。
- `local`：创建本地提交但不推送，适用于未配置远端或离线场景。
- 文档与项目内知识默认采用工程配置；项目经验提升到全局资产库始终产生独立的 `review` 变更，不能继承项目的 `direct` 策略。
- Run 的分析状态与发布状态相互独立；内容生成成功后，push 或建 PR 失败只令发布进入可重试的失败状态，不重新调用 Agent。
- Gitea 是首个 PR provider；其它 Git 远端在没有 provider 适配器时可使用 `direct/local`，或仅推送审核分支并给出外部建 PR 提示。

### 2.4 权限规格（FR-MGR-008、FR-MGR-017）

- 鉴权后端可插拔（ADR-0023）：`local` 本地账密（零依赖默认）/ `oidc` Keycloak（`CHRONICLER_AUTH_BACKEND` 切换，接线见 ../runbooks/deploy.md 与 scripts/wire-chronicler.sh）。
- 角色：admin（全部 + 配置/触发/用户管理）/ user（只读）；OIDC 模式下 Keycloak groups 映射：boss→admin、其余→user，首次登录自动 provisioning 本地用户记录。
- 找回密码：OIDC 模式由 admin 在用户页「重置密码」（经 Keycloak Admin API，支持临时密码标记）；SMTP 未配置时 Keycloak 自助找回不可用。
- 账号事实源唯一：OIDC 模式下本地密码登录仅 admin 应急可用（登录页入口收起于「本地应急账号登录」链接），本地表为 OIDC 首次登录的影子记录、只读；local 模式下本地账号全功能。
- 审计：登录（含 OIDC）、配置变更、触发、工具启停均落 `audit_log`。

### 2.5 前端页面清单

v1 已落地：`/login`（SSO 主入口 + 本地应急） · 首页（组件卡片：状态/启停/自启开关/日志/详情，FR-ENV-003、FR-MGR-022） · 工程（登记/同步/覆盖项） · 任务（Run 列表/日志/报告/触发） · 配置（全局默认 harness 选择 + harness 增删改，FR-MGR-019/020；components/prompts 查看，prompts 可编辑） · 用户管理(admin)。
规划：`/` 项目全景（FR-MGR-012） · `/reports` 报告中心 · `/assets` 资产库（FR-MGR-013/014） · `/review` Git 变更审核（文件 diff、PR 状态、批准/驳回/外部链接） · `/settings` 系统设置（FR-MGR-015）

### 2.6 里程碑

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| M1 骨架 ✅ | FastAPI + OIDC + 工具总览 + Agent 终端 + 接入 compose | boss/dev 登录看到不同视图 |
| M2 代码源与执行器 | repo 同步 + harness 执行器（宿主直起）+ 手动触发 + SSE 日志 | 跑一次"总结 README"任务看流式日志 |
| M3 内置任务 | 6 类内置任务 + prompt 库 + 报告中心 | 日报/gap 报告产出，可见性正确 |
| M4 待审闭环 | Git review 区 + 文档/卡片 PR + shadow/全局资产库 + 文档站更新 | 页面可查看 Run 产物 diff；项目经验经两级审核上升全局库；可配置 direct/local |
| M5 CI 综合 | Jenkins 结果接入 + 综合报告 + webhook 触发 | 综合报告含构建结果；push 触发任务 |
| M6 加固 | supervisor Nuitka 打包 + prompt 加密 + 审计 + 限流 | 二进制内无源码与明文 prompt |

## 3. HOW

架构图、执行管线、并发控制、CI 集成机制、部署形态见 ../how/manager-architecture.md。技术选型决策见 ../adr/0007-manager-separate-from-jenkins.md、0008、0009、0010（同目录）。
