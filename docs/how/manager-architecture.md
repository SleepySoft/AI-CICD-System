# Manager 架构与执行机制

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
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
│ Manager 后端 (FastAPI)                                                       │
│ ├─ API 层        /api/repos /agents /prompts /tasks /runs /reports /review  │
│ ├─ 调度器        APScheduler（cron 定时 + 手动触发 + Webhook 触发）           │
│ ├─ 任务框架      TaskType 注册表（内置 6 类 + 自定义）                        │
│ ├─ 执行器        docker.sock 拉起 agent-runner 容器执行                       │
│ ├─ CI/CD 集成    Jenkins REST API 轮询/推送 + Gitea Webhook                  │
│ └─ 鉴权          Keycloak OIDC；boss/dev 角色 → 报告可见性过滤               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 存储：Postgres(库 manager) │ 文件卷 reports/ │ Qdrant（向量化供 RAG）        │
└─────────────────────────────────────────────────────────────────────────────┘
        │ 拉起执行                │ 拉取构建结果          │ 接收 push 事件
        ▼                        ▼                      ▼
  agent-runner 一次性容器    Jenkins（构建/测试）    Gitea / GitHub（代码源）
```

### 2.2 技术栈机制

FastAPI + SQLAlchemy 2 + Alembic（异步、自带 OpenAPI）；APScheduler（AsyncIO + SQLAlchemyJobStore，任务定义在 DB）；前端 Vue3 + Element Plus 构建为静态文件托管；实时日志用 SSE（单向推送足够，比 WebSocket 简单）；LLM 走 OpenAI 兼容抽象层（云端/本地 Ollama 可切换）。决策理由见 ADR：../adr/0007-manager-separate-from-jenkins.md、0008、0009、0010（同目录）。

### 2.3 Agent 执行管线

```
触发(cron/手动/webhook)
  → 创建 Run(queued)，冻结输入快照(commit range、prompt 版本、CI 上下文)
  → 同步代码：git clone/pull 到缓存卷 repos/<id>/（凭证从 secret 注入，落盘前脱敏）
  → collector 采集上下文（diff/文档/需求/CI 结果），超限自动摘要分片
  → 渲染 prompt（模板变量替换）
  → docker run aisystem/agent-runner（--rm，CPU/内存限额，网络仅限内网+LLM 出口）
       env: LLM_API_KEY 等经 --env-file 注入；挂载: 仓库只读 + 输出卷可写
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

Manager 作为 compose 核心服务（无 profile）：挂载 `manager_data`（报告/日志）、`repos_cache`（仓库缓存）、`/var/run/docker.sock`（拉起 agent-runner）。Caddy 加 `app.localhost → manager:8000`。

运行拓扑（ADR-0019）：Manager **保持容器化**，不整体搬出宿主；宿主侧仅允许一个极简引导器（开机自启 + 栈健康看门狗，异常时执行 `scripts/up.sh` 救栈），不做任何业务管理。M6 Nuitka 二进制化后可重评宿主直跑形态。

保密加固（BR-009，M6）：agent-runner 内流程代码 Nuitka 编译为二进制；内置 prompt 构建期加密为资产文件、运行期用 FERNET_KEY 解密（密钥只在 .env/secret，不进镜像层）；Manager 镜像多阶段构建，最终层不含源码。

## 3. 决策与备选

| 决策点 | 选择 | ADR |
|--------|------|-----|
| 分析任务不放 Jenkins | Manager 独立承载 | ../adr/0007-manager-separate-from-jenkins.md |
| 调度器 | APScheduler 而非 Celery+Redis | ../adr/0008-apscheduler-over-celery.md |
| 报告存储 | 文件卷 + DB 元数据 | ../adr/0009-reports-on-file-volume.md |
| 前端 | Vue3（M1-M2 可 Jinja2/htmx 过渡） | ../adr/0010-vue3-frontend.md |
| 运行拓扑 | 容器化 + 宿主引导器，不整体搬出 Docker | ../adr/0019-manager-runtime-topology.md |
