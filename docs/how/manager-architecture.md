# Manager 架构与执行机制

> 版本：v1.6 · 日期：2026-09-02 · 状态：生效
> 定位：Manager 的内部实现机制（架构、执行管线、CI 集成、部署形态）；规格契约见 ../what/manager.md
> 关联需求：FR-MGR-003 ~ FR-MGR-030

## 1. WHY / WHAT 摘要

Manager 管"分析与洞察"，消费 CI 结果、不替代 CI（Non-Goal 见 ../why/vision.md）。数据模型、API、权限等契约见 ../what/manager.md。

## 2. HOW

### 2.1 总体架构（Container 级）

```
┌──────────────────────── 前端 (Vue3 SPA, 经 Caddy: app.localhost) ───────────┐
│ 仪表盘 │ 代码源 │ Agent配置 │ Prompt库 │ 任务 │ 运行记录 │ 报告中心 │ 待审区 │
└──────────────────────────────▲──────────────────────────────────────────────┘
                               │ OIDC 登录 (Keycloak) + REST/SSE
┌──────────────────────────────┴──────────────────────────────────────────────┐
│ Manager 后端 (FastAPI) —— docker 宿主侧进程（compose 外，ADR-0020）          │
│ ├─ API 层        /api/repos /agents /prompts /tasks /runs /reports /review  │
│ ├─ 调度器        APScheduler（cron 定时 + 手动触发 + Webhook 触发）           │
│ ├─ 任务框架      TaskType 注册表（5 个任务 → 4 个 Prompt 家族 + 自定义）      │
│ ├─ 执行器        宿主直起 harness 进程（ADR-0021）；本地 Docker API 控栈      │
│ ├─ CI/CD 集成    Jenkins REST API 轮询/推送 + Gitea Webhook                  │
│ └─ 鉴权          Keycloak OIDC；boss/dev 角色 → 报告可见性过滤               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 存储：Postgres(库 manager) │ 文件卷 reports/ │ Qdrant（向量化供 RAG）        │
└─────────────────────────────────────────────────────────────────────────────┘
        │ 拉起执行                │ 拉取构建结果          │ 接收 push 事件
        ▼                        ▼                      ▼
  harness 进程（宿主执行）   Jenkins（构建/测试）    Gitea / GitHub（代码源）
```

### 2.2 技术栈机制

FastAPI + SQLAlchemy 2 + Alembic（异步、自带 OpenAPI）；APScheduler（AsyncIO + SQLAlchemyJobStore，任务定义在 DB）；前端 Vue3 + Element Plus 构建为静态文件托管；实时日志用 SSE（单向推送足够，比 WebSocket 简单）；LLM 走 OpenAI 兼容抽象层（云端/本地 Ollama 可切换）。决策理由见 ADR：../adr/0007-manager-separate-from-jenkins.md、0008、0009、0010（同目录）。

### 2.3 Agent 执行管线

```
触发(cron/手动/webhook)
  → 同步代码：每次 trigger 前 fetch/checkout/reset 到配置分支；首次 clone
  → 执行 Git + command probes，生成有效输入快照并与上次成功 Run 比较
  → 自动触发按 change_policy 决定 queued 或 skipped；手动触发只提示不跳过
  → 创建 Run，冻结基线/增量、prompt 版本、CI 上下文
  → collector 采集上下文（diff/文档/需求/CI 结果），超限自动摘要分片
  → 渲染 prompt（模板变量替换 + 已配置资源能力(skill)的访问途径注入，FR-MGR-015）
  → 宿主直起 harness 进程（ADR-0021：命令 + 参数模板来自 agent_profile；
       LLM_API_KEY 等经环境变量注入；仓库为宿主真实路径，无挂载翻译；
       不可信/CI 任务可选 terminal-runtime 沙箱执行）
  → 流式回传日志(SSE)；超时/异常 → Run(failed) + 错误归因(网络/配额/解析失败)
  → output_parser 解析（约定产出为 frontmatter+Markdown，或 JSON 指令块）
  → persister：报告/文档/知识候选写入 project_shadow 工作树并登记产物
  → Git publisher：当前由 Chronicler 以 direct 提交并推送 main；review/local 后续扩展
  → 通知：门户角标 + 可选 webhook（企业微信/邮件，后置）
```

并发控制：全局信号量（默认 2 个并发 Run）+ 每工程代码仓串行锁 + 每 shadow 仓串行锁。shadow 锁覆盖分支准备、Agent 写入、提交与工作树恢复，避免不同 harness 并发切换同一工作树；harness 自身仍可因全局状态另设串行锁。

任务解析（ADR-0034）：`registry.TASK_TYPES` 是新任务清单，记录 `name/prompt/mode/desc`；runner 在冻结 Run 快照前解析任务，将 `prompt_name`、`task_mode`、`repo_head` 与 `ci_context` 注入模板。配置 API 分别提供 task-types 和 prompts，前端因此显示 5 个可执行任务与 4 个可编辑模板。`LEGACY_TASK_TYPES` 只在执行旧 task_def 时解析，不参与新工程预置。

增量探测（ADR-0035）：`change_detection` 在 Agent 之前运行。它从同一 task_id 最近一次 success Run 读取 source_snapshot，计算 Git 提交/diff，并串行执行配置的 command probes（宿主 shell、工程仓 cwd、默认超时 60 秒）。探测结果写入 input_snapshot 和 Prompt；自动无增量写入 skipped Run，不启动 harness。probe 失败令状态 unknown 并继续运行；同步/其它前置失败则写入脱敏的 failed Run，避免把环境故障误判为无变化或静默漏档。

### 2.3.1 Git 发布管线（FR-MGR-009/013/014/026）

当前已实现 direct 基础管线：冻结策略与 shadow HEAD → 获取 shadow 仓锁 → 确认工作树干净 → 切换或规范分支为 `main` → Agent 写产物 → Chronicler 提交 → push `HEAD:main` → 独立记录 publication。该路径不创建任务分支或 PR；远端默认分支基线比较尚未实现。

以下为 ADR-0033 规定的完整目标管线，其中 review/local、direct 基线冲突保护和全局经验提升仍待实现：

1. Run 创建后冻结目标默认分支及 `base_commit`；Chronicler 获取对应 shadow 仓锁。
2. `review` 模式从基线创建 `chronicler/task-<task_id>/run-<run_id>`；`local` 使用本地任务分支；`direct` 不建任务分支，直接在干净的目标默认分支生成和提交。
3. Agent 仅写产物；Chronicler 检查工作树、记录文件清单，以固定机器身份执行 `git add/commit`，提交信息包含 Run/Task ID。
4. `review` 将任务分支 push 到远端，通过 Gitea `POST /api/v1/repos/{owner}/{repo}/pulls` 创建 PR；以 repo + head branch 查询已有 PR，使失败重试不重复创建。
5. `direct` 在 push 前 fetch 并比较远端默认分支与 `base_commit`；一致时将任务提交快进到默认分支，不一致则 `publish_status=conflict`，不自动 rebase、不 force push。
6. `local` 保留本地任务分支与提交，不访问远端。
7. 发布结果单独记录；v1 direct 已产生 `pending|unchanged|local|pushed|failed`，完整流程扩展为 `pr_created|merged|conflict`；发布失败可从既有提交重试，不重新执行 harness。
8. 项目经验提升全局时，从已批准的项目提交复制候选内容并附来源元数据，在全局资产库创建新的任务分支与 PR；它是独立审核，不做跨仓库 Git merge。

Gitea 凭据仅由 Chronicler 的 Git publisher/API client 读取。PR 首版由 Gitea 页面完成批准与合并，Chronicler 审核页负责展示 diff、状态和跳转；后续可增加代理合并 API，但不改变上述提交所有权。

### 2.4 CI/CD 集成（只消费、不越界）

| 方向 | 机制 |
|------|------|
| Manager ← Jenkins | 任务执行前后调 Jenkins REST（`/job/xxx/lastBuild/api/json`）拉取构建结果写入 `ci_context`；综合报告按时间窗聚合 |
| Manager ← Gitea | Webhook（push/merge）→ `/api/webhooks/gitea` → 触发绑定该 repo 的任务（可配防抖） |
| Manager → CI/CD | 只读消费结果；分析任务不反向操控流水线 |

### 2.5 部署形态

运行拓扑（ADR-0020，推翻 ADR-0019）：Manager 不在 compose 内，而是部署在 **docker 宿主侧的 supervisor 进程**——跟随 dockerd 同环境部署（WSL 原生 dockerd → 部在 WSL；Docker Desktop → 部在 Windows；Linux/macOS → 本机），经本地 Docker API（unix socket / npipe，尊重 `DOCKER_HOST` 与显式配置）控制栈。推荐 Linux/WSL，Windows 可用但不推荐。supervisor 同时吸收引导职责：开机自启（平台原生服务管理器：systemd / launchd / 任务计划）+ 探活；组件异常时执行 `scripts/up.sh` 救底座栈（ADR-0029 起 up.sh 不再拉起 supervisor 本体，supervisor 自愈由服务管理器 Restart 策略负责）；不维护任何跨边界会话。

入口与依赖：管理台仍为 `app.localhost`——v1 已落地为 Caddy `extra_hosts: host-gateway` 回源 `host.docker.internal:8600`，supervisor 监听宿主 8600（本地账密，不接 Keycloak；ADR-0023）；工具 API 全经 Caddy `*.localhost` 消费，无新开端口。数据仍落 `${DATA_ROOT:-./data}/private/chronicler`（NFR-008，ADR-0026 二分），supervisor 直读 `.env`（缺失时主入口提示并退出，ADR-0029）。

平台选择原则："在哪个环境跑，就用哪个环境的 docker"。Docker Desktop 仅作用户自带许可的可选运行时（NFR-001 注记），免费默认路径为 WSL/原生 dockerd（docker 须 systemd 常驻，`vmIdleTimeout=-1` 作双保险）。

保密加固（FR-MGR-029/030，ADR-0036）：`RuntimeProfile` 统一解析安装根和资源路径；source 使用结构化 YAML Catalog，sealed 使用编译模块中的 AES-GCM key 解密 bundle。Runner 在 sealed 下只冻结 Prompt name/version/hash，stdin harness 不落临时文件，文件 harness 执行后删除 `prompt.md`。static/config 作为公开资源外置；组件不进入核心发行包，仍按 ADR-0027 从安装根 components/ 与 DATA/components 扫描。

## 3. 决策与备选

| 决策点 | 选择 | ADR |
|--------|------|-----|
| 分析任务不放 Jenkins | Manager 独立承载 | ../adr/0007-manager-separate-from-jenkins.md |
| 调度器 | APScheduler 而非 Celery+Redis | ../adr/0008-apscheduler-over-celery.md |
| 报告存储 | 文件卷 + DB 元数据 | ../adr/0009-reports-on-file-volume.md |
| 前端 | Vue3（M1-M2 可 Jinja2/htmx 过渡） | ../adr/0010-vue3-frontend.md |
| 运行拓扑 | docker 宿主侧 supervisor，跟随 dockerd 同环境部署（推翻容器化+引导器） | ../adr/0020-manager-out-of-docker-supervisor.md |
| Agent 执行位置 | 用户自装 harness，宿主执行；terminal-runtime 降为可选沙箱（部分推翻 ADR-0017） | ../adr/0021-agent-user-installed-harness.md |
| v1 形态 | SQLite + 本地账密 + 一次性会话（闭环 ADR-0022 悬置的单机瘦身项） | ../adr/0023-supervisor-v1-form.md |
| AI 产物 Git 发布 | Agent 只生成内容；Chronicler 统一分支、提交、push、建 PR；全局提升强制二次审核 | ../adr/0033-chronicler-owned-git-publication.md |
| 任务与 Prompt 分类 | 5 个任务通过 registry 复用 4 个职责明确的 Prompt 家族，旧类型仅兼容 | ../adr/0034-task-prompt-family-registry.md |
| sealed 运行与发行 | 构建时固化 Profile；结构化 Catalog；AES-GCM bundle；Nuitka standalone；组件外置 | ../adr/0036-sealed-runtime-prompt-catalog.md |
