# Runbook: 手动启动与调试 Chronicler

> 版本：v1.4 · 日期：2026-09-27 · 状态：生效
> 适用：本机（Windows Docker Desktop 或 WSL）开发/调试 supervisor 与底座
> 关联：chronicler/（主入口 chronicler/__main__.py）、scripts/up.sh、ADR-0020/0023

## 目的

脱离 systemd/开机自启，手动拉起全系统并具备断点调试能力；知道日志在哪、改了代码怎么生效。

## 步骤

### 1. 启动底座（通常无需手动——supervisor 自启钩子会自动拉起标记自启的组件，FR-MGR-022）

仅首次部署或需要拉起非自启组件时手动：

自启组件由 supervisor autostart 钩子自动拉起（FR-MGR-022）；非自启组件在首页工具面板点「部署」
（docker 组件定义在各组件目录 `chronicler/components/<name>/compose.yml`，ADR-0027）。

### 2. 启动 supervisor（唯一入口，行为处处一致）

`.env` 由 chronicler/app/config.py **自动加载**（已存在的进程环境变量优先）；
`python -m chronicler serve` 是唯一启动方式，缺 .env 会提示并退出：

```powershell
# Windows（调试：前台跑；常驻：把主入口命令加入开机启动项/任务计划）
chronicler\.venv-win\Scripts\python.exe -m chronicler serve
```

```bash
# WSL/Linux（常驻：bash chronicler/scripts/install-service.sh 注册 systemd）
chronicler/.venv/bin/python -m chronicler serve
```

### 3. 验证

```bash
bash scripts/verify-chronicler.sh    # WSL；Windows 用浏览器访问 http://127.0.0.1:8600/api/health
```

预期：`{"ok":true,"service":"chronicler",...}`；有底座时 `http://app.localhost` 200。

## 调试要点

| 目标 | 方法 |
|------|------|
| 断点调试 | supervisor 是普通本地进程（ADR-0020 的红利）：PyCharm/VS Code 直接调试 `chronicler/__main__.py`（已内置包上下文垫片，脚本模式也能跑）；更规范的做法是运行配置选 **Module name: `chronicler`**（等价 `python -m chronicler`） |
| 热重载 | `uvicorn chronicler.app.main:app --reload --port 8600`（改 Python 即重启） |
| 前端 | 改 `chronicler/app/static/*` 后**刷新浏览器即可**，无需重启 |
| 配置 | `chronicler/config/harness.yaml`、`chronicler/config/settings.yaml` 与组件 `plugin.yaml` 改文件即热生效；`data/private/chronicler/config/` 同名文件覆盖内置；页面「配置」可改全局默认 harness 与增删改 harness（admin，同样落 DATA 覆盖） |
| 服务日志 | 前台终端直接看；systemd 常驻用 `journalctl --user -u chronicler` |
| Run 日志 | `data/private/chronicler/runs/<run_id>/run.log`（或页面「任务」→ 日志） |
| Run 提示词 | `data/private/chronicler/runs/<run_id>/prompt.md`（或页面「任务」→ 提示词；渲染后全文同时落库 task_runs.prompt_text） |
| 容器日志 | 首页组件卡片「日志」按钮，或 `docker logs aisystem-<name>-1` |
| 数据库 | `data/private/chronicler/chronicler.db`（SQLite，可用 `sqlite3` 或 DBeaver 直查） |

## 重置损坏的工程克隆

适用：同步提示「工作区克隆已损坏（不是独立 git 仓库）」；旧版本在点击「重置克隆」后
仍提示同一错误（2026-09-27 Windows 回归验证，见 AGENTS.md 已知环境坑）。

1. 更新代码后，停止旧 Chronicler 进程，再按上文「启动 supervisor」启动，使修复生效。
2. 用 admin 登录，在「工程」页找到目标工程，点击「重置克隆」，确认重建。
   此操作会删除该工程工作区中的本地文件与未提交修改；需要保留的文件请先另行备份。
3. 当前实现会处理只读文件；若提示「无法清理工作区克隆」，先关闭占用该目录的终端、编辑器或
   agent 会话并检查目录权限，再重试。清理失败时不会继续同步。
4. 验证：页面提示「已重置并重新拉取」，刷新后该工程显示远端最近提交，同步错误清空。
   再点击同步应成功，不再出现损坏克隆提示。

重置保留工程登记、Run 档案与 Shadow 报告，但已删除的未提交修改无法自动恢复，
只能从操作前另存的备份取回。路径异常时系统拒绝删除；请检查该工程克隆目录是否为
指向其它位置的符号链接或 Windows junction，勿对宿主源码目录执行 `git reset --hard`。

## 任务触发与执行记录

1. 在工程页或任务页点击执行，核对增量预览后确认。按钮在预览与提交期间禁用。
2. 收到「已接收：Run #…」后，在执行记录查看该编号。「排队中」表示等待执行资源；
   「准备中」表示正在同步仓库、探测输入和准备 Prompt；「运行中」才表示 harness 已启动。
   接收时间与开始时间分开展示，等待期间开始时间为空。
3. 网络报错后可在当前页面重试；页面会复用本次请求标识，已经接收的请求返回同一 Run。
   若提示已有活动 Run，先查看提示中的编号，待结束后再触发新的执行。
4. 工程执行期间同步或重置提示工作区正在使用时，待该工程任务结束后重试。
   页面轮询约 3 秒，日志约 2 秒；无需因短暂显示延迟连续点击。

改动后重启 supervisor，并刷新桌面或移动页面。回归验证命令见
[组件测试](testing.md#任务链路回归)。

## 认知维护因 Shadow 治理资源缺失而停止

旧版只在创建空 Shadow 仓库时复制治理模板；已有 `.git` 就直接返回。因此仓库存在不代表其中已有 `SKILL.md`、`.cognitive-state.yaml` 和治理模板，认知任务遇到这种历史仓库会按规则停止。

新版准备流程会验证 Shadow 是独立 Git 仓库，并对工作区干净、同时缺少 `SKILL.md` 和状态文件的历史仓库补齐治理文件、提交迁移。已有文件和历史保持不变，基线保持空值，状态为 `initializing`，首次任务从当前源码事实建立认知。如果治理文件仅部分缺失，或工作区有未提交改动，准备流程会停止并报告原因；应先检查并恢复对应版本的资源，不要删除目录或虚构基线。

```powershell
git -C data/public/shadow/ai-cicd-system-shadow status --short
Get-Content -Encoding UTF8 data/public/shadow/ai-cicd-system-shadow/.cognitive-state.yaml
```

内置 Codex harness 在 Shadow 工作目录使用 `workspace-write`，额外可写根目录清空，源码作为只读输入；源码同步由 supervisor 执行。认知维护成功还要求状态中的提交等于本次目标提交，`maintenance.last_run` 指向本次运行记录，记录的 `run_id`、`status: success` 和目标提交一致。只有停止摘要时保留报告，但运行标记失败。

2026-09-27 修复工程 2 的历史 Shadow：原有 68 个文件内容不变，迁移提交 `e8b648a` 已推送；Run 27 因未完成维护修正为失败，原报告保留。操作前元数据备份在 `data/private/chronicler/repair-backups/20260927-151227/metadata.json`，变更写入审计。回滚治理迁移前应检查独立 Shadow 仓库并评审对应提交，不能删除整个目录。

## 任务日志和工程说明乱码

日志文件使用 UTF-8，不代表写入前的字符串没有损坏。Windows PowerShell 5.1 的文件读取编码、控制台输出编码和 `$OutputEncoding`（向原生命令传入管道文本）是不同设置。未指定编码读取 UTF-8 文件、用错误编码传递中文后，即使最终写成 UTF-8，内容仍可能已经变成问号或 U+FFFD。Python 的 UTF-8 设置不能单独控制 PowerShell。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fix-powershell-utf8.ps1
```

脚本保留并备份现有 CurrentUserAllHosts profile，添加幂等的 UTF-8 设置，包括文件命令默认编码、控制台与管道编码、Python 子进程编码。执行后打开新终端；内置 Codex harness 已启用 shell profile。自定义命令使用 `-NoProfile` 时仍需自己显式设置编码，读取源码使用 `Get-Content -Encoding UTF8`。PowerShell 5.1 的默认 UTF-8 写入可能带 BOM，且换行可能为 CRLF；仓库文件仍须遵守 LF，可用 Python 显式按 UTF-8 和 LF 写入。

```powershell
chronicler/.venv-win/Scripts/python.exe -m unittest chronicler.tests.test_text_encoding chronicler.tests.test_shadow_template -q
```

历史日志中的 U+FFFD 或已存入数据库的问号无法仅靠切换编码还原。保留原日志，修复环境后重跑；工程说明应根据实际用途重新填写。本次工程 2 的说明在旧备份中也已是问号，因此重写为“GitHub 源码仓库（SSH 同步）”，未声称恢复原文。日志面板遇到 U+FFFD 会提示已有内容损坏。

需要回滚 shell 设置时，将脚本打印的原始备份复制回 `$PROFILE.CurrentUserAllHosts`，然后打开新终端。重启 Chronicler 后，新的准备流程、harness 和完成校验才会完整生效。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 页面 500 且日志有 UnicodeDecodeError | Windows GBK 解码坑 | 确认代码已含 `encoding="utf-8"` 修复（AGENTS.md 已知环境坑） |
| OIDC 登录 token 交换失败 | 代理拦截 127.0.0.1 | 确认进程走 trust_env=False；shell 里测试用 `curl --noproxy '*'` |
| app.localhost 502 | supervisor 没起或 Caddy 未重载 | 先验 127.0.0.1:8600 直连；再在首页工具面板重启 caddy（或 `docker start aisystem-caddy-1`） |
| 改了代码不生效 | 后台旧进程还在 | 停掉 8600 端口的旧进程再启动（Windows：`Get-NetTCPConnection -LocalPort 8600` 找 PID） |
| PyCharm 调试报端口占用 | 后台服务实例占着 8600 | 调试配置加环境变量 `CHRONICLER_PORT=8601` 错开（经 8601 直连调试，不影响正式入口）；或先停服务实例 |
| 容器全部消失 / `http://localhost` 与各 `*.localhost` 全灭（仅 8600 直连可用） | Docker Desktop/引擎未启动 | supervisor autostart 钩子会自动按平台拉起引擎（Windows 启动 Docker Desktop、Linux/WSL systemd/service、macOS `open -a Docker`）并按标记拉起组件；仍失败则手动启动 Docker Desktop 后重启 supervisor；先确认仓库根 `.env` 存在 |

## 回滚（如适用）

调试出问题想回到干净状态：底座组件在首页工具面板重启（或 `docker restart aisystem-<name>-1`）；
supervisor 直接 Ctrl+C 重启进程即可，数据都在 `data/private/chronicler/` 不受影响。
