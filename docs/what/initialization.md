# Web 初始化与环境设置规格

> 版本：v1.3 · 日期：2026-09-04 · 状态：生效
> 定位：独立 initialization 模块对用户、组件和 API 暴露的契约；不规定内部线程、数据库实现或具体组件接线命令。
> 关联需求：FR-INIT-001 ~ FR-INIT-011、NFR-002、NFR-004、NFR-010

## 1. WHY 摘要

首次部署是一个长耗时、跨组件且容易部分成功的过程。用户需要单一、可解释、可恢复的 Web 路径，
而组件仍须保持可选、外置、自描述。决策依据见
[ADR-0037](../adr/0037-single-entry-web-init.md) 与
[ADR-0038](../adr/0038-bootstrap-mode-and-declarative-initialization.md)。

## 2. WHAT

### 2.1 生命周期与可见性

实例状态只有以下对外语义：

| 状态 | 页面行为 | API/后台行为 |
|------|---------|-------------|
| `bootstrap` | 打开任意页面均引导到 `/setup` | 只开放 setup、health 和静态资源；不启动调度器与组件自启 |
| `configuring` | 恢复草稿或执行进度 | 与 bootstrap 相同；允许安全中断和续接 |
| `restart-required` | 显示已保存内容和明确重启指引，自动探测服务恢复 | 不宣称新进程级配置已生效 |
| `ready` | 正常登录页；admin 可进入 `/setup` 环境设置中心 | 普通业务能力启用；setup 写 API 要求 admin |
| `repair` | 正常登录页展示配置漂移告警 | 不自动重新开放未认证初始化入口 |

`ready` 是不可由环境故障自动逆转的安全边界。`.env` 丢失、Docker 不可用或组件故障只能进入
失败关闭/repair，不得重新获得未认证写权限。

旧版实例升级时，如已存在 Chronicler 数据库和用户但没有 initialization 记录，系统必须先关闭公开
引导能力，再允许 normal/repair 启动；不得把“缺少新表”解释为“全新安装”。

### 2.2 八阶段用户流程

1. **欢迎与解锁**：解释数据、端口和组件影响；用一次性引导码换取 HttpOnly 引导会话。
2. **环境预检**：以“通过 / 警告 / 阻塞”卡片展示检测结果，每项附修复动作和重新检测按钮。
3. **部署方案**：提供“仅 Chronicler / 推荐底座 / 完整底座 / 自定义”四种方案；卡片展示用途、
  资源估算和自动加入的依赖，不用技术名词要求用户理解拓扑。自定义组件按 `plugin.yaml.group`
  分组；数据库、缓存、统一入口等仅依赖组件不提供独立选择，而在选中使用者后自动展示并加入。
4. **基础配置**：只收集 Chronicler 自有配置及域名、时区、数据根等共享设置；端口等组件专属参数
  由组件声明，并在选择组件后即时检查。
5. **管理员与组件配置**：先创建本地恢复管理员，再按所选组件分组显示字段；秘密可一键生成，
   离开输入框后只显示“已设置”。高级字段默认折叠。
6. **计划确认**：以组件时间线展示 `skip/create/start/wait/configure/verify/restart`；警告和破坏性
  动作置顶。此阶段可主动使用唯一一次凭据显示与 JSON 下载机会：账号完整显示，密码摘要固定显示
  首字符、8 个星号和尾字符，密钥/令牌完整显示；下载文件包含完整值并明确要求转存密码管理器。
7. **执行**：顶部显示总体阶段和预计剩余项；每个组件独立显示排队、执行、成功、失败、被依赖阻塞，
   可展开脱敏日志。关闭页面不停止执行；支持仅重试失败项。
8. **完成**：展示可访问入口、已启用能力、后续可选项和重启状态；不再次展示密码或 token。

向导始终提供“保存并退出”；执行前可返回修改，执行开始后修改配置会生成新计划，不能静默改变
正在运行的计划。

### 2.3 部署方案契约

方案只是组件标签查询，不是写死的组件列表：

| 方案 | 选择规则 |
|------|---------|
| `chronicler-only` | 不选择环境组件，只完成本地管理员与 Chronicler 配置 |
| `recommended` | 选择 `profiles` 含 `recommended` 的组件及依赖闭包 |
| `full` | 选择 `profiles` 含 `full` 且平台兼容的组件及依赖闭包 |
| `custom` | 用户显式选择；依赖自动补齐且不可在被依赖时单独取消 |

组件选择结果必须说明来源：`explicit`、`profile` 或 `dependency-of:<name>`。依赖环、缺失依赖、
平台不兼容和端口冲突是计划阻塞项；资源不足默认是警告，由组件声明决定是否提升为阻塞。

### 2.4 组件 `setup.yaml` 契约

`setup.yaml` 与 `plugin.yaml`、compose、hook 同处组件目录，缺失时组件仍可在普通工具面板手工部署，
但不会进入批量初始化方案。首版结构：

```yaml
schema_version: 1
profiles: [recommended, full]
depends_on: [postgres]
dependency_only: false
conflicts_with: []
platforms: [windows, linux, darwin]
resources:
  memory_mb: 512
  disk_mb: 1024
fields:
  - key: EXAMPLE_PASSWORD
    label: 管理员密码
    kind: secret
    secret_type: password
    required: true
    generate: password
    generate_length: 24
    rotation_risk: coordinated
    help: 登录该组件后台的管理员密码；轮换后须同步更新使用该账号的自动化工具。
readiness:
  kind: container-health
  timeout_sec: 300
initialize_hook: hooks/initialize.py
```

字段契约：

- `fields[].key` 必须在初始化模块允许写入的环境变量命名空间内；`kind` 支持
  `text|secret|integer|boolean|choice|path|port`。
- 字段可声明 `default`、`placeholder`、`pattern`、`choices`、`min/max`、`help`；秘密不得声明真实默认值。
- 需要进入一次性凭据摘要的非秘密账号字段声明 `summary: account`；核心不按字段名猜测账号含义。
- `kind: secret` 必须由组件提供非空 `help`，并声明 `secret_type`（`password|client-secret|encryption-key|
  api-token|access-key`）、16～128 的 `generate_length` 和 `rotation_risk`（`low|coordinated|critical`）。
  核心只解释和渲染这些通用枚举，不按字段名或组件名猜测用途；具体用途、保存位置与轮换影响均由
  字段所属组件说明。
- `depends_on` 只引用组件稳定名称；依赖决定执行顺序，不隐含“启用后一定注入 Agent”。
- `dependency_only: true` 表示组件不能被用户直接选择，只能由 `profiles` 或其他组件的依赖闭包加入；
  适用于 PostgreSQL、Redis、Caddy 等共享基础服务。选择页必须显示自动加入原因，计划仍完整列出该组件。
- 选择页分组和用途说明复用 `plugin.yaml` 的 `group`、`desc`，不在 `setup.yaml` 维护第二份展示文案。
- `readiness.kind` 首版支持 `container-health|http|tcp|process`；检查目标可引用已收集字段，但响应和
  日志不得保存秘密。
- `initialize_hook` 可选。hook 接收版本化 JSON 上下文，以 JSON Lines 输出检查/配置结果；必须实现
  `check` 和 `apply`，使执行器遵守先检查后修改。hook 路径不得越出组件目录。
- 所有组件名称、字段、默认值、端口、客户端、认证源、账号及接线知识只能存在于组件自己的声明、
  资源或 hook 中，禁止进入核心 initialization 模块。跨组件接线由能力消费方拥有：例如某应用需要
  身份服务客户端时，由该应用 hook 通过声明依赖获得通用上下文并维护自己的客户端，身份服务不反向
  硬编码消费应用清单。

`schema_version` 大于当前模块支持版本时，组件标记为“需要升级 Chronicler”且不可选；同版本新增的
可选字段必须有默认语义，不得改变旧声明行为；删除、改名或改变字段语义必须提升 major schema 版本。

### 2.5 计划与运行模型

```
SetupDraft
  id, revision, current_stage, profile, selected_components,
  non_secret_values, secret_presence, updated_at

SetupPlan
  id, draft_revision, environment_fingerprint, plan_hash,
  components[], actions[], warnings[], destructive_actions[], created_at

SetupRun
  id, plan_id, status(planned|running|waiting_restart|success|failed|canceled),
  started_at, finished_at, summary

SetupStep
  run_id, component, phase(preflight|persist|admin|deploy|ready|configure|verify|finalize),
  status(pending|running|success|failed|blocked|skipped), input_hash,
  attempt, started_at, finished_at, error_class, error_summary, log_ref
```

草稿只保存非秘密值和“秘密是否已设置”；秘密进入服务端秘密暂存区并最终原子写入 `.env`，不得进入
`SetupDraft`、`SetupPlan`、步骤日志或 API 响应。计划绑定草稿版本与环境指纹；任一变化令旧计划
失效并要求重新确认。

唯一例外是用户在计划确认后主动调用的一次性凭据导出：只返回当前进程中新输入且属于当前选择的秘密，
不反向读取 `.env`；响应设置 `no-store`，服务端原子消耗机会，第二次调用必须拒绝。前端立即触发本地
JSON 下载，只在当前页面内保留显示摘要，不写入草稿、计划、日志、localStorage 或诊断数据。

### 2.6 执行语义

全局阶段顺序固定为：

```
preflight → persist-config → create-admin → deploy → readiness → configure → verify → finalize
```

- 组件之间按有向无环依赖图调度；无依赖节点可有限并行，默认并发数 2。
- 单组件的 `deploy → readiness → configure → verify` 严格串行。
- 每步先执行 `check`：目标状态已满足且 `input_hash` 未变化则 `skipped/success`，否则执行 `apply`。
- `create-admin` 是全局步骤：密码只用于生成不可逆哈希；同名 admin 已存在且身份匹配时幂等跳过，
  角色或来源冲突时阻塞并要求用户处理，不覆盖既有账号。
- 一个组件失败时，其依赖后继标记 `blocked`；无关分支继续。用户可仅重试失败/阻塞分支。
- 取消只在步骤边界生效，不强杀正在执行的 compose/hook；不自动删除已经创建的数据。
- 最终完成条件为：`.env` 已原子持久化、本地 admin 存在、全部必需步骤验证成功、没有待确认重启。

### 2.7 API 契约

```
GET    /api/setup/status                 生命周期、当前草稿/运行摘要（不含秘密）
POST   /api/setup/unlock                 一次性引导码换 HttpOnly 引导会话
GET    /api/setup/preflight              执行环境预检
GET    /api/setup/catalog                方案、组件及字段元数据
GET    /api/setup/draft                  当前草稿（秘密仅返回 configured: bool）
PUT    /api/setup/draft                  保存当前阶段输入
POST   /api/setup/plan                   生成固定计划
GET    /api/setup/plans/{id}             查看计划
POST   /api/setup/secrets/export          一次性显示并下载本次新输入的凭据
POST   /api/setup/plans/{id}/execute     确认并启动
GET    /api/setup/runs/{id}              总体与组件进度
GET    /api/setup/runs/{id}/events       SSE 进度与脱敏日志
POST   /api/setup/runs/{id}/retry        重试失败/阻塞分支
POST   /api/setup/runs/{id}/cancel       请求在步骤边界取消
POST   /api/setup/finalize               完成并关闭引导能力
GET    /api/setup/history                admin 查看历史运行
GET    /api/setup/diagnostics            admin 导出脱敏诊断
```

引导模式下，读取 catalog/preflight/status 只返回非敏感信息；所有保存、计划和执行操作必须持有引导
会话。ready 后全部写接口及 history/diagnostics 要求 admin，普通用户无权调用。

### 2.8 安全与错误呈现

- 首次启动生成高熵一次性引导码，只保存哈希；控制台输出含 URL fragment 的打开地址，fragment 不进入
  HTTP access log，前端立即用它换取 `HttpOnly + SameSite=Strict` 短期 cookie 并从地址栏清除。
- 引导 cookie 最长有效 24 小时并采用滑动空闲超时；完成初始化时服务端立即令其失效并返回删除 cookie。
  当 `bootstrap_closed_at` 已存在时，即使浏览器仍携带旧 cookie 也只能进入正常登录页。
- 默认引导监听仅允许本机访问；远程初始化必须由操作者显式配置监听地址并提供引导码。
- 错误响应采用稳定 `code`、用户可读 `message`、`remediation`、可选 `details_ref`；不得把 subprocess
  原始命令行、环境变量或秘密返回浏览器。
- UI 用“发生了什么 / 为什么 / 如何修复”三段式提示；保留技术详情折叠区与诊断引用，避免只显示
  exit code。

## 3. HOW 摘要

模块边界、状态存储、执行器、hook 隔离和与 FastAPI 的最小接线见
[初始化架构](../how/initialization-architecture.md)。