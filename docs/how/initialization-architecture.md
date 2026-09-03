# Web 初始化模块架构与执行机制

> 版本：v1.1 · 日期：2026-09-03 · 状态：生效
> 定位：`chronicler.app.initialization` 的内部模块边界、状态机、执行器和安全机制；用户操作步骤不在本文定义。
> 关联需求：FR-INIT-001 ~ FR-INIT-011、NFR-002、NFR-010

## 1. WHY / WHAT 摘要

初始化是可恢复的系统协调事务，不是若干按钮依次调用 shell。外部流程、组件声明和 API 契约见
[Web 初始化规格](../what/initialization.md)，架构依据见
[ADR-0038](../adr/0038-bootstrap-mode-and-declarative-initialization.md)。

## 2. HOW

### 2.1 模块边界

实现集中在一个 Python 包，除应用入口挂载和正常模式判定外，不向现有业务模块散布初始化分支：

```
chronicler/app/initialization/
├── __init__.py          对外只暴露 lifecycle 与 router
├── lifecycle.py         bootstrap/configuring/ready/repair 判定与模式闸门
├── security.py          一次性引导码、引导 cookie、admin 权限适配
├── store.py             模块自有 SQLite 表与事务；使用独立短连接且不改业务表
├── catalog.py           扫描/校验组件 setup.yaml，生成只读 catalog
├── preflight.py         Docker、Compose、目录、端口、资源和存量资源检查
├── config_store.py      `.env` 解析、字段白名单、秘密暂存、原子写入与脱敏
├── planner.py           profile 展开、依赖闭包、冲突检查、环境指纹和固定计划
├── orchestrator.py      DAG 调度、并发上限、取消、续接和重试
├── router.py            `/setup`、`/api/setup/*`、SSE 与脱敏诊断响应
└── static/              独立 index.html、setup.js 与 setup.css
```

组件特定内容位于：

```
chronicler/components/<name>/
├── plugin.yaml
├── setup.yaml
├── compose.yml
└── hooks/initialize.py   # 可选，check/apply/verify
```

`initialization` 复用 `tools.py` 中不依赖 HTTP 请求的 Docker/compose 生命周期函数；组件特定逻辑只在
组件目录声明与 hook 中出现。后续若执行器继续增长，再从 orchestrator 拆分，不提前制造空模块。

### 2.2 应用接线与模式闸门

主入口只增加一次模式解析：

```
serve
  → lifecycle.detect()
  ├─ 首次且未完成 → bootstrap runtime（安全默认配置）
  ├─ 已完成且配置有效 → normal runtime
  └─ 已完成但配置缺失/无效 → fail closed，打印恢复指引
```

FastAPI 工厂按模式装配：

- bootstrap：挂载 setup router、health 与 setup 静态资源；不导入/启动 tasks scheduler、业务 routers、
  autostart worker，避免“路由虽拦截但后台已经运行”。
- normal：装配现有业务 routers、scheduler、autostart，并把 setup router 置于 admin 权限模式。
- 中间件再做一层路径 allowlist，防未来新增 router 时误暴露；两层防御均由 lifecycle 提供。

初始化模块不得根据 users 表是否为空自动判断可重开。`installation` 单例记录一旦写入
`bootstrap_closed_at` 就永久关闭公开能力；恢复必须由本机命令显式轮换引导码并审计，且不能清除
完成历史。

兼容迁移遵循失败关闭：若 installation 表不存在，但默认或进程显式指定的数据目录中已有 Chronicler
数据库及用户，则创建 `legacy-adopted` 的关闭记录，而不是生成引导码。恢复入口为主入口下的
`setup-recover` 管理子命令，仅允许在宿主交互终端执行并要求二次确认；Web API 不提供等价操作。

### 2.3 状态存储

模块在同一个 Chronicler SQLite 文件中自建以下表，DDL 和迁移由 `initialization.store` 独占：

```
installation       singleton, schema_version, lifecycle, bootstrap_token_hash,
                   bootstrap_closed_at, active_run_id, completed_plan_hash, timestamps
setup_drafts       id, revision, stage, profile, selections_json, values_json, secret_refs_json
setup_plans        id, draft_revision, environment_fingerprint, plan_hash,
                   plan_json, confirmed_at, created_at
setup_runs         id, plan_id, status, cancel_requested, started_at, finished_at, summary_json
setup_steps        id, run_id, component, phase, ordinal, status, input_hash,
                   attempt, error_class, error_summary, timestamps
setup_events       id, run_id, step_id, level, event_type, message, data_json, at
```

原则：

- 数据库中不存秘密值；`secret_refs_json` 只记录字段已设置和暂存引用。
- 计划 JSON 是执行时唯一输入；执行开始后不再读可变草稿。
- `plan_hash` 对规范化计划计算 SHA-256；确认动作记录该 hash。
- 一个实例只允许一个 active run。v1 以单 supervisor 进程为部署约束，重启时根据 `active_run_id` 接管
  running 运行；多 worker/多进程部署需在引入租约后才可开放。
- 事件表保存供状态页、SSE 与诊断响应使用的脱敏结构化摘要，不保存子进程原始环境或命令行。

状态表与引导能力文件归 Chronicler 私有数据，固定落在 `Cfg.DATA/initialization/` 及同一 SQLite 中，
不建立跨组件共享私有目录。v1 向导中的“数据根”仅配置组件 `DATA_ROOT`；若操作者通过进程环境显式
设置 `CHRONICLER_DATA`，必须在首次启动前设置，向导不在线迁移 Chronicler 自身数据库。

### 2.4 配置和秘密流水线

```
浏览器输入
  → 字段级校验
  → secret 值只进入进程内短期暂存区 / 非 secret 进入 draft
  → 生成计划时仅引用 secret-present 字段集合与非秘密配置摘要
  → persist-config 步骤在锁内合并现有 .env
  → fsync 临时文件 → 同目录原子 replace → 收紧文件权限
  → 清除暂存秘密与请求体引用
```

`.env` 写入器保留未知键和注释，只有 catalog 白名单字段可由向导修改。现有进程环境优先级保持不变；
若外部环境变量覆盖了 `.env`，预检和计划必须明确标识“由进程环境接管”，避免用户误以为页面修改会
生效。日志脱敏器至少覆盖：所有 secret 字段原值、URL userinfo、Authorization/Cookie 头、常见
token/key/password 赋值形式。

秘密暂存不承诺跨进程恢复：写入 `.env` 前若服务重启，界面保留“已配置但需重新输入”的 presence，
用户必须重新输入。Python 无法保证普通对象的内存安全擦除，因此安全边界是不落持久状态、缩短存活
时间并在请求/计划对象不再需要时主动解除引用，而不是宣称可靠清零。字段名匹配
`secret|password|token|api_key|credential` 却未声明 `kind: secret` 时，catalog 直接拒绝该组件；
诊断包生成后再次以已知秘密值和常见凭据模式扫描，命中则中止导出。

跨平台写入使用目标同目录临时文件，写入后 flush + fsync，再以 `os.replace` 替换且不先删除有效旧文件；
POSIX 尝试收紧为 `0600`。所有子进程显式使用
`encoding="utf-8", errors="replace"`，不依赖 Windows 系统编码。

首次生成引导码与未落盘的秘密不依赖默认 `CHRONICLER_SECRET`。引导 cookie 使用独立随机密钥签名，
仅保存在 private 数据目录；初始化完成后删除明文能力并保留 token hash 和关闭时间作为审计证据。

### 2.5 Catalog 与计划器

`catalog.py` 对每个 setup 文件执行 JSON-Schema 等价校验，并拒绝：未知 schema version、重复字段 key、
依赖缺失、hook 越界、非法环境变量名、不支持的平台与 readiness 类型。Catalog 错误按组件隔离展示，
但被选组件的错误会阻塞计划。

计划器算法：

1. 读取固定 catalog revision、用户方案和显式选择。
2. 计算传递依赖闭包，记录每个选择来源。
3. 检查 conflict、平台、端口和有向环；稳定拓扑排序（同层按组件名）。
4. 调用每种通用 executor 的只读 `inspect`，判断动作是 skip、create、start、configure 或 verify。
5. 生成规范化 actions 与 warnings；计算 environment fingerprint 和 plan hash。
6. 保存不可变计划。执行前重新计算环境指纹；关键漂移令计划过期，非关键漂移转警告。

v1 环境指纹包含 catalog 内容 hash 与当前平台；plan hash 另包含固定组件图、非秘密配置摘要和秘密字段
presence。执行前强制复核 draft revision、catalog revision、Docker/Compose、目录与目标端口；不包含
秘密明文、动态日志或无关容器。

指纹输入采用键排序、无无关空白的规范 JSON 后计算 SHA-256；容器启动时间、日志和检查时间不参与。
容器存在/运行变化属于关键漂移，因为它会改变计划动作；执行中的正常状态变化由既有 run 和逐步 check
处理，不反过来作废已经启动的 run。

### 2.6 DAG 执行器

orchestrator 运行于受控后台 worker，不绑定浏览器请求生命周期：

```
                 ┌─ component A: deploy → ready → configure → verify ─┐
persist → admin ─┤                                                     ├─ finalize
                 └─ component B: deploy → ready → configure → verify ─┘
                                      │
                                      └─ component C（依赖 B）...
```

- 全局并发以 semaphore 限制，默认 2；Docker pull/compose 可另设并发 1，防止磁盘和网络争抢。
- 状态变更与事件先提交数据库，再推送 SSE；浏览器断开不影响 worker。
- 进程终止遗留的 `running` 步骤由启动钩子接管；success/skipped 步骤直接跳过，其余步骤幂等重试。
- hook、compose 和健康检查有独立超时。超时分类为可重试，不直接推断目标未创建。
- retry 增加 step attempt，旧错误保留在事件历史；输入变化必须生成新 plan/run，不能在旧 run 上重试。
- cancel 设置数据库标志；worker 在当前原子步骤结束后停止调度新步骤，将未开始项标为 canceled。
- 步骤是否完成以其 `check` 观察到的目标状态为准，不以 `apply` 返回成功为准；`apply` 部分完成或超时后
  重试仍先 check，已存在的客户端、账号、认证源和容器必须被识别并复用。

### 2.7 通用执行器与组件 hook

`executors.py` 只认识动作类型，不认识组件名称：

| 执行器 | `check` | `apply` |
|--------|---------|---------|
| persist | 比较受管字段摘要 | 原子合并 `.env` |
| admin | 按用户名检查本地恢复管理员 | 以现有密码哈希器建 admin，不覆盖冲突账号 |
| deploy | 检查目标容器/进程与 compose config | 调用组件 deploy hook或 compose up |
| readiness | 执行声明的 health/http/tcp/process probe | 只等待并周期检查，不修改配置 |
| initialize-hook | 调用 hook `check` | 调用 hook `apply` 后再次 `check` |
| verify | 运行声明检查或 hook `verify` | 无隐式修复；失败交由 retry |
| finalize | 检查 admin、必需步骤和 restart | 关闭引导能力并记录完成 hash |

hook 通过外部进程执行，沿用 sealed Profile 的 `CHRONICLER_COMPONENT_PYTHON` 约定。调用参数只含 action；
受控 runner 仅注入宿主执行必需变量和该组件依赖闭包声明的配置字段。stdout/stderr 只在失败时截断、
脱敏后形成事件摘要，退出码非零与超时分别归类。

source 模式默认使用当前 Python；sealed 模式在 preflight 中强制验证 `CHRONICLER_COMPONENT_PYTHON`
存在且满足组件 hook 声明的 Python 依赖。秘密只在执行对应 hook 的最小环境中短时注入，不出现在命令行、
上下文 JSON 或子进程继承环境的其它字段中。

首批迁移时，原脚本能力按所有权拆分：Keycloak realm/client/scope 进入 Keycloak initialize hook；Gitea
管理员与 OIDC 认证源进入 Gitea initialize hook；跨组件参数由依赖上下文引用，但配置逻辑仍由目标组件
拥有。核心不得出现 `if component == "keycloak"` 一类分支。

### 2.8 前端组织

初始化 UI 独立于现有大 SPA，以无构建依赖的原生 JavaScript/CSS 提供自己的入口和状态：

- `setup.js` 按 API 返回的 stage 渲染有限状态机，不从 URL 参数推断进度。
- 步骤导航只允许跳到服务端判定可访问的阶段；所有校验以后端为准，前端即时校验仅改善体验。
- 执行页用 SSE 接收增量事件，断线后以最后 event id 续传，并定时用 run GET 做最终校准。
- 组件采用概览卡片 + 右侧配置抽屉；默认只显示推荐字段，高级项折叠。
- 错误卡固定包含摘要、影响、建议操作、重试按钮和诊断引用；技术日志默认折叠。
- 不把秘密放入 Vue 全局持久状态、localStorage、URL、事件数据或错误上报。

### 2.9 最小侵入点

允许修改现有模块的范围限定为：

1. `__main__.py`：以 lifecycle 代替无条件 `require_env()`，保留已初始化实例失败关闭。
2. `main.py`：改为 app factory，按模式挂载 router 和启动 worker。
3. `tools.py`：把 Docker/compose 通用原语提取为无 FastAPI 依赖的 lifecycle service；现有 API 不变。
4. `db.py`：只暴露连接/事务能力；初始化表 DDL 留在 initialization/store.py。
5. sealed 构建清单：纳入 initialization/static 与 schema，不把组件 setup/hook 编入核心。

除此之外，认证、工程、任务和 Run 模块不感知初始化步骤。业务模块只看到 normal 模式或根本不被装配。

### 2.10 测试边界

| 层 | 必测内容 |
|----|---------|
| 单元 | setup schema、依赖闭包/环/冲突、稳定 plan hash、状态转换、脱敏、`.env` 合并 |
| API | bootstrap allowlist、引导码交换/失效、ready 后 admin 权限、秘密不回显 |
| 中断恢复 | worker 在 deploy/configure 后终止并接管；已满足步骤不重复 apply |
| 组件契约 | 每个 setup.yaml 校验；initialize hook 的 check/apply/check 幂等性 |
| 集成 | 临时数据目录 + 隔离 compose project 执行 recommended 方案，成功后无重复资源 |
| 安全 | 日志/DB/诊断包秘密扫描；完成后旧引导码重放失败；已初始化缺 `.env` 不重开 |

干净安装集成测试至少覆盖 Windows Docker Desktop、WSL 原生 dockerd 和 Linux 原生 dockerd；Windows
覆盖排除端口、Docker 启动慢、代理开关与 NTFS ACL，WSL 覆盖 `/mnt/c` 路径和代理绕过，Linux 覆盖
docker socket 权限。所有平台均执行首次安装、中途终止、恢复、重复执行和旧版实例安全收养场景。

### 2.11 分阶段实施顺序

该模块体量较大，按可独立验收的纵向切片交付，避免一次提交同时改入口、部署和全部组件：

1. **骨架与安全闸门**：建立 initialization 包、状态表、bootstrap/normal app factory、一次性引导码
  和独立静态页；只支持 `chronicler-only`，先证明“未初始化可进入、完成后不可重开”。
2. **配置与计划**：实现 setup schema、catalog、`.env` 原子合并、秘密脱敏、依赖图和只读计划预览；
  尚不执行 compose。
3. **通用执行器**：提取 Docker/compose lifecycle service，实现持久步骤、SSE、租约、中断续接和
  通用 readiness；先用无接线要求的小组件做端到端验证。
4. **核心底座方案**：为 postgres、keycloak、caddy、gitea 补 setup.yaml；将 Keycloak/Gitea 接线迁入
  各自 initialize hook，形成首个 recommended 方案。
5. **完整方案与设置中心**：逐组件补声明和验证，开放 full/custom、增量计划、诊断导出和 admin 模式。
6. **切换唯一入口**：完成 Windows/WSL/Linux 干净安装测试后更新 runbook 与 AGENTS.md，回收被取代的
  up/wire 脚本；验证脚本保留为测试资产还是迁为 hook，按其是否仍有独立诊断价值逐项决定。

每个切片都必须保持当前脚本路径可用，直到第 6 步明确切换；不得在新路径尚未通过干净安装测试时
提前移动脚本。

### 2.12 升级与契约迁移

- `installation.schema_version` 低于当前版本时先执行模块自有数据库迁移；历史 plan/run/step 保持只读。
- 新版组件声明新增必需配置或检查时，ready 实例进入 repair 提示并生成 admin 可确认的增量计划，
  不自动执行，也不重开 bootstrap。
- 高于当前支持版本的 setup.yaml 不尝试降级解析；组件保持不可选并给出升级提示。
- hook JSON 上下文携带独立 `protocol_version`；不兼容版本在计划阶段阻塞，不在执行中临时猜测。

## 3. 决策与备选

| 决策点 | 选择 | 依据 |
|--------|------|------|
| 首次无 `.env` | 受限 bootstrap runtime；已初始化仍失败关闭 | ADR-0038 |
| 代码组织 | 独立 initialization 包及独立前端入口 | ADR-0038 |
| 组件差异 | 组件目录 setup.yaml + 可选 hook | ADR-0027/0038 |
| 失败恢复 | 持久步骤 + check/apply 幂等重试，不自动删数据 | ADR-0038 |
| 完成后用途 | 同模块转为 admin 环境设置中心 | 避免重复批量部署机制 |