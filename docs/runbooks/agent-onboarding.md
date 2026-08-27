# Runbook: 接入一家新 Agent（用户自装 harness 模式）

> 版本：v1.1 · 日期：2026-08-27 · 状态：生效
> 适用：supervisor（Chronicler）已在宿主运行（见 deploy.md 第二节），操作者为 admin 角色
> 关联：chronicler/config/harness.yaml、ADR-0021（用户自装 harness）、ADR-0023（v1 仅 once 会话）、FR-MGR-019
> 旧的 manager/agents.yaml + scripts/agents/*.sh 安装脚本体系已随 manager/ 删除，本文替代旧流程

## 目的

让 supervisor 能驱动一家新 agent 执行任务。ADR-0021 起，agent CLI 的**安装与登录由用户在自己的
宿主（WSL）自行完成**，supervisor 只登记一条 harness 命令模板；terminal-runtime/ATR 降为可选
sandbox profile，不再承担 agent 生命周期。

## 步骤

1. **用户自装并登录 CLI**（在 WSL 宿主，非容器）：
   - pip 系：如 `pip install aider-chat`（建议装进独立 venv 或 pipx，避免污染系统环境）；
   - npm 系 CLI 自行处理（`npm install -g <cli>` 等）；
   - OAuth/网页登录类：装完人工跑一次交互式登录，凭据落在用户 HOME 下持久生效；
   - API key 类：把密钥写进 `.env`（如 `LLM_API_KEY=...`），**绝不写进 YAML**。
2. **登记 harness**：在 `chronicler/config/harness.yaml` 的 `harnesses:` 下加一条记录。
   配置热更新，改文件即生效；需环境差异化时，在 `data/chronicler/config/harness.yaml`
   放同名文件覆盖包内置配置。字段：

   | 字段 | 说明 |
   |------|------|
   | `name` | 唯一标识 |
   | `desc` | 一句话描述（页面展示用） |
   | `command_template` | 启动命令模板，支持变量 `{prompt_file}` `{report_file}` `{repo_dir}`；以 shell 执行（cwd = 工程仓库目录） |
   | `session` | 会话能力声明：`once`（一次性，v1 仅此）/ `persistent`（预留，暂拒绝执行，ADR-0021 TBD） |
   | `env` | 注入的环境变量；`"${VAR}"` 从 supervisor 进程环境解析（密钥不落明文） |
   | `timeout_sec` | 单次执行超时 |

   参照内置三条记录：aider / kimi / shell（冒烟假 harness）。
3. **页面触发验证**：supervisor 页面 → 用内置任务 daily-report 跑一次，观察 Run 成功
   （先用 shell harness 验证模板渲染与报告落盘，再切真实 agent）。

## 验证

```bash
bash scripts/verify-chronicler.sh   # supervisor 冒烟（含受保护 API 401 检查）
```

预期输出：脚本通过；页面上新 harness 出现在可选项中，daily-report Run 成功且报告可查看。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 命令模板变量未替换（2026-08-27） | `command_template` 中变量名拼错或未用花括号 | 只用 `{prompt_file}` `{report_file}` `{repo_dir}` 三个变量，对照内置记录 |
| Run 报命令不存在 / CLI 不在 PATH（2026-08-27） | CLI 装在用户 venv/pipx，supervisor 进程 PATH 不含它 | `command_template` 写绝对路径（如 `/home/u/.local/bin/aider`） |
| 密钥未生效（`${VAR}` 解析为空）（2026-08-27） | `${VAR}` 引用的是 supervisor 进程环境，非登录 shell 环境 | systemd 场景把变量写进仓库根 `.env`（unit 已配 `EnvironmentFile=-$REPO/.env`）；前台运行则先 `export VAR=...` 再启动 |
| 声明 `session: persistent` 的 harness 被拒执行（2026-08-27） | v1 仅支持一次性会话（ADR-0023） | 改回 `once`；persistent/resume 语义待后续版本（ADR-0021 TBD） |

## 回滚

删除 `chronicler/config/harness.yaml`（或 `data/chronicler/config/harness.yaml` 覆盖文件）中
对应记录即下架，热更新立即生效；宿主上 CLI 本体与登录凭据由用户自行清理。
