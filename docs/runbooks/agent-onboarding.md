# Runbook: 接入一家新 Agent（用户自装 harness 模式）

> 版本：v1.3 · 日期：2026-09-01 · 状态：生效
> 适用：supervisor（Chronicler）已在宿主运行（见 deploy.md 第二节），操作者为 admin 角色
> 关联：chronicler/config/harness.yaml、ADR-0021（用户自装 harness）、ADR-0023（v1 仅 once 会话）、FR-MGR-019
> 旧的 manager/agents.yaml + scripts/agents/*.sh 安装脚本体系已随 manager/ 删除，本文替代旧流程

## 目的

让 supervisor 能驱动一家新 agent 执行任务。ADR-0021 起，agent CLI 的**安装与登录由用户在自己的
宿主（WSL）自行完成**，supervisor 只登记一条 harness 命令模板；terminal-runtime/ATR 降为可选
沙箱组件（ADR-0021），不再承担 agent 生命周期。

## 步骤

1. **用户自装并登录 CLI**（在 WSL 宿主，非容器）：
   - pip 系：如 `pip install aider-chat`（建议装进独立 venv 或 pipx，避免污染系统环境）；
   - npm 系 CLI 自行处理（`npm install -g <cli>` 等）；
   - OAuth/网页登录类：装完人工跑一次交互式登录，凭据落在用户 HOME 下持久生效；
   - API key 类：把密钥写进 `.env`（如 `LLM_API_KEY=...`），**绝不写进 YAML**。
2. **登记 harness**：两种方式任选，效果等同（页面写操作落 `data/private/chronicler/config/harness.yaml`
   覆盖文件，内置文件保持只读）：
   - 配置页：admin 在「配置 → Harness 列表 → + 新增 Harness」填表保存（推荐）；
   - 改文件：在 `chronicler/config/harness.yaml` 的 `harnesses:` 下加一条记录（或直接编辑
     `data/private/chronicler/config/harness.yaml` 覆盖文件），配置热更新、改文件即生效。
   字段：

   | 字段 | 说明 |
   |------|------|
   | `name` | 唯一标识 |
   | `desc` | 一句话描述（页面展示用） |
   | `command_template` | 启动命令模板，以 shell 执行；变量 `{prompt_file}` `{report_file}` `{repo_dir}` `{shadow_dir}`（自动按平台加引号） |
   | `stdin_prompt` | `true` = prompt 全文经 stdin 管道传入（kimi / codex exec 的 stdin 模式）；缺省 = harness 自己读 `{prompt_file}`（如 aider `--message-file`） |
   | `report_mode` | `file`（缺省）= harness 写 `{report_file}`（如 codex `-o`）；`stdout` = supervisor 捕获 stdout 落为报告（如 kimi `--print`） |
   | `cwd` | `repo`（缺省，工程仓库目录）\| `shadow`（工程 shadow 库目录）；任务定义可在「任务 → 编辑」覆盖（解析顺序：任务覆盖 > harness 默认 > 工程仓库） |
   | `session` | 会话能力声明：`once`（一次性，v1 仅此）/ `persistent`（预留，暂拒绝执行，ADR-0021 TBD） |
   | `env` | 注入的环境变量；`"${VAR}"` 从 supervisor 进程环境解析（密钥不落明文） |
   | `timeout_sec` | 单次执行超时 |

   参照内置记录：aider / kimi / kimi-continue / codex / dummy（dummy 为冒烟假 harness）。
3. **设置默认 harness**：配置页「全局默认 Harness」选择并保存（admin）；也可在工程页对单个工程
   覆盖，或在任务页对单个任务覆盖（解析顺序：任务级 > 工程级 > 全局默认，FR-MGR-020）。
4. **页面触发验证**：supervisor 页面 → 用内置任务 operational_reporter 跑一次，观察 Run 成功
   （先用 dummy harness 验证模板渲染与报告落盘，再切真实 agent）。

## 验证

```bash
bash scripts/verify-chronicler.sh   # supervisor 冒烟（含受保护 API 401 检查）
```

预期输出：脚本通过；页面上新 harness 出现在可选项中，operational_reporter Run 成功且报告可查看。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 命令模板变量未替换（2026-08-27） | `command_template` 中变量名拼错或未用花括号 | 只用 `{prompt_file}` `{report_file}` `{repo_dir}` `{shadow_dir}` 四个变量，对照内置记录 |
| Run 报命令不存在 / CLI 不在 PATH（2026-08-27） | CLI 装在用户 venv/pipx，supervisor 进程 PATH 不含它 | `command_template` 写绝对路径（如 `/home/u/.local/bin/aider`） |
| 密钥未生效（`${VAR}` 解析为空）（2026-08-27） | `${VAR}` 引用的是 supervisor 进程环境，非登录 shell 环境 | systemd 场景把变量写进仓库根 `.env`（unit 已配 `EnvironmentFile=-$REPO/.env`）；前台运行则先 `export VAR=...` 再启动 |
| Run 成功但报告为空/未产出（2026-09-01） | harness 把回复打印到 stdout 而没写 `{report_file}` | 把该 harness 的 `report_mode` 设为 `stdout`（如 kimi）；或命令里加 `-o {report_file}`（如 codex） |
| 任务日志/报告乱码（2026-09-01） | CLI 按本地编码（Windows GBK）输出 | runner 已改为二进制逐行解码（UTF-8→回落本地编码）后按 UTF-8 落盘，并默认注入 `PYTHONUTF8=1`；页面查看接口同样逐行归一解码。**已被旧版替换符（U+FFFD）写坏的历史日志无法恢复，需重跑该任务** |
| Run 一直显示"运行中"（2026-09-01） | 进程被中断/supervisor 重启/执行线程死亡，状态未落库 | 调度器每分钟做状态悬挂扫描：queued 超 10 分钟或 running 超过 harness 超时+2 分钟仍未结束 → 自动标记失败（error_class=悬挂）；历史悬挂记录在下次扫描时自动清理 |
| 声明 `session: persistent` 的 harness 被拒执行（2026-08-27） | v1 仅支持一次性会话（ADR-0023） | 改回 `once`；persistent/resume 语义待后续版本（ADR-0021 TBD） |

## 回滚

配置页删除对应记录即下架（会写入 `data/private/chronicler/config/harness.yaml` 覆盖文件）；
要完整恢复包内置清单，删除该覆盖文件即可；宿主上 CLI 本体与登录凭据由用户自行清理。
