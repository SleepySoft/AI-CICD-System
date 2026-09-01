# ADR-0032 手动 Agent 会话的上下文注入契约（约定文件 + 动态 SKILL + chai 三通道）

> 日期：2026-09-01 · 状态：已接受
> 关联：ADR-0021/0024/0025/0030/0031；chronicler/app/runner.py（_render_prompt）、chronicler/app/registry.py（injectable_components）；需求 FR-MGR-024/025、UR-010

## 背景

自动 Run 的注入已经实现（runner.py `_render_prompt`：组件 L0 摘要 + SKILL 路径，agent 按需自读，ADR-0024/0025）。手动 vibe coding（浏览器 Web 终端或本地终端进入受管工程）需要同样的上下文，但交互式 shell 里没有 prompt 模板可注入，必须把上下文落到**工程内文件**。

三家目标 CLI 的 skill/指令发现机制调查（2026-09-01，官方文档 + 本机实测）：

- **Kimi Code CLI**（Moonshot 官方帮助中心 / kimi-cli.com）：读项目根及任意子目录 `AGENTS.md`（`~/.kimi/AGENTS.md` 为全局）；项目级 skills 目录 `.kimi/skills/`、`.claude/skills/`、`.codex/skills/`（品牌组）+ `.agents/skills/`（通用组），用户级 `~/.kimi/skills/` 等同理；启动时把全部 skill 的 name/path/description 注入系统提示，按需读 SKILL.md，`/skill:<name>` 强制加载；项目根 = 最近含 `.git` 的祖先。
- **Codex CLI**（官方 CLI 手册镜像 + openai/codex 仓库 docs + 本会话实测）：`AGENTS.md` 三层（`~/.codex/AGENTS.md` < 仓库根 < 当前目录）；用户级 skills `~/.codex/skills/**/SKILL.md`；项目级 `.codex/skills/` 与 `.agents/skills/` 均生效（本会话同时加载两处）；`--no-project-doc` 可关闭项目文档。
- **Claude Code**（code.claude.com 官方文档）：读 `CLAUDE.md`（根/子目录/`CLAUDE.local.md`），**不读 AGENTS.md**，但支持在 CLAUDE.md 中 `@AGENTS.md` 导入桥接；项目级 skills `.claude/skills/<name>/SKILL.md`，个人 `~/.claude/skills/`；description 常驻上下文、调用时全文加载；支持嵌套目录限定名与符号链接。

结论：三家都会同时读工程目录与用户家目录；**项目级是随 git 走、可动态生成的注入通道，用户级是宿主状态不应写入**。官方 Codex 手册所在域（developers.openai.com）本网络直连 403，经代理可达（重定向至 learn.chatgpt.com/docs/codex-manual.md）。

## 决策

手动 agent 会话采用三通道注入，全部落在工程工作区内（`data/workspace/repos/<id>/`），不写用户级目录：

1. **约定文件**：生成/刷新工作区根 `AGENTS.md`（Chronicler 能力摘要 + 组件 SKILL 索引 + 路径约定）；另生成 `CLAUDE.md` 以 `@AGENTS.md` 桥接 Claude Code。
2. **动态 SKILL**：按 harness 类型在 `.codex/skills/chronicler/`、`.kimi/skills/chronicler/`、`.claude/skills/chronicler/` 各生成一份瘦 SKILL.md（frontmatter name/description + 指向 Chronicler 能力正文与组件 SKILL 的路径），实现“动态生成 skill 注入 chronicler 功能与路径”。
3. **chai 包装命令**：cd 到工程 → 刷新上述文件 → 设置会话环境（含代理变量）→ 拉起目标 CLI（`kimi --print` / `codex exec` / `claude -p`）。手动与自动会话共用 `registry.injectable_components()` 同一数据源。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 只写用户级 skills（`~/.kimi/skills/` 等） | 宿主状态影响所有项目、不可随工程迁移/共享，与“数据显式落宿主、工程可重建”原则冲突 |
| 只靠系统提示/env 注入 | 交互式 shell 会话没有稳定 prompt 通道；CLI 的 `--system-prompt` 只覆盖单次调用 |
| 只写约定文件不生成 skills | Claude 不读 AGENTS.md（需 `@AGENTS.md` 桥接）；长能力正文应放 skill 按需加载，避免约定文件膨胀 |
| chai 只做 cd+拉起 CLI | 不刷新注入文件则上下文陈旧；无统一入口不便脚本化 |

## 后果

正面：三家 agent 都在工程内拿到同一份 Chronicler 上下文；注入内容与自动 Run 同源，无第二份事实；文件随工作区可重建、可审计。
负面：Windows 无符号链接便利，三家 skills 目录各放一份瘦 SKILL.md（内容指针共享，小文件复制）；生成文件混入工作区 git 状态，需约定 .gitignore 或提交策略；P0 未实现前该契约仅文档化。
同步：requirements/functional/manager.md（FR-MGR-025）、docs/runbooks/web-terminal.md、docs/README.md 索引；实现后落 chai 引导脚本与生成器（复用 runner.py 上下文组装）。
