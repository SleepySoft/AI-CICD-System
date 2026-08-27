# Manager 架构与执行机制

> 版本：v1.1 · 日期：2026-08-27 · 状态：生效
> 定位：Manager 的内部实现机制（架构、执行管线、CI 集成、部署形态）；规格契约见 ../what/manager.md
> 关联需求：FR-MGR-003 ~ FR-MGR-011

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
│ ├─ 任务框架      TaskType 注册表（内置 6 类 + 自定义）                        │
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
  → 创建 Run(queued)，冻结输入快照(commit range、prompt 版本、CI 上下文)
  → 同步代码：git clone/pull 到缓存卷 repos/<id>/（凭证从 secret 注入，落盘前脱敏）
  → collector 采集上下文（diff/文档/需求/CI 结果），超限自动摘要分片
  → 渲染 prompt（模板变量替换 + 已配置资源能力(skill)的访问途径注入，FR-MGR-015）
  → 宿主直起 harness 进程（ADR-0021：命令 + 参数模板来自 agent_profile；
       LLM_API_KEY 等经环境变量注入；仓库为宿主真实路径，无挂载翻译；
       不可信/CI 任务可选 terminal-runtime 沙箱执行）
  → 流式回传日志(SSE)；超时/异常 → Run(failed) + 错误归因(网络/配额/解析失败)
  → output_parser 解析（约定产出为 frontmatter+Markdown，或 JSON 指令块）
  → persister：报告→reports/ 卷+元数据入库；知识卡片→ai-inbox/；索引→Qdrant
  → 通知：门户角标 + 可选 webhook（企业微信/邮件，后置）
```

并发控制：全局信号量（默认 2 个并发 Run）+ 每仓库串行锁（避免同仓库并发分析造成 diff 基线错乱）。

### 2.4 CI/CD 集成（只消费、不越界）

| 方向 | 机制 |
|------|------|
| Manager ← Jenkins | 任务执行前后调 Jenkins REST（`/job/xxx/lastBuild/api/json`）拉取构建结果写入 `ci_context`；综合报告按时间窗聚合 |
| Manager ← Gitea | Webhook（push/merge）→ `/api/webhooks/gitea` → 触发绑定该 repo 的任务（可配防抖） |
| Manager → CI/CD | 只读为主；`deviation-analysis` 可建 Gitea issue；不反向操控流水线 |

### 2.5 部署形态

运行拓扑（ADR-0020，推翻 ADR-0019）：Manager 不在 compose 内，而是部署在 **docker 宿主侧的 supervisor 进程**——跟随 dockerd 同环境部署（WSL 原生 dockerd → 部在 WSL；Docker Desktop → 部在 Windows；Linux/macOS → 本机），经本地 Docker API（unix socket / npipe，尊重 `DOCKER_HOST` 与显式配置）控制栈。推荐 Linux/WSL，Windows 可用但不推荐。supervisor 同时吸收引导职责：开机自启（平台原生服务管理器：systemd / launchd / 任务计划）+ 探活 + 异常时执行 `scripts/up.sh` 救栈；不维护任何跨边界会话。

入口与依赖：管理台仍为 `app.localhost`——v1 已落地为 Caddy `extra_hosts: host-gateway` 回源 `host.docker.internal:8600`，supervisor 监听宿主 8600（本地账密，不接 Keycloak；ADR-0023）；工具 API 全经 Caddy `*.localhost` 消费，无新开端口。数据仍落 `${DATA_ROOT:-./data}/chronicler`（NFR-008），supervisor 直读 `.env`。

平台选择原则："在哪个环境跑，就用哪个环境的 docker"。Docker Desktop 仅作用户自带许可的可选运行时（NFR-001 注记），免费默认路径为 WSL/原生 dockerd（docker 须 systemd 常驻，`vmIdleTimeout=-1` 作双保险）。

保密加固（BR-009，M6）：supervisor 流程代码 Nuitka 编译为独立二进制（即交付形态）；内置 prompt 构建期加密为资产文件、运行期用 FERNET_KEY 解密（密钥只在 .env/secret，不进二进制）。

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
