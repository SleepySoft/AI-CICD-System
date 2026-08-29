# Runbook: 手动启动与调试 Chronicler

> 版本：v1.0 · 日期：2026-08-27 · 状态：生效
> 适用：本机（Windows Docker Desktop 或 WSL）开发/调试 supervisor 与底座
> 关联：chronicler/、scripts/up.sh、scripts/start-chronicler.ps1、ADR-0020/0023

## 目的

脱离 systemd/开机自启，手动拉起全系统并具备断点调试能力；知道日志在哪、改了代码怎么生效。

## 步骤

### 1. 启动底座（通常无需手动——supervisor 自启钩子会自动拉起标记自启的组件，FR-MGR-022）

仅首次部署或需要拉起非自启组件时手动：

```powershell
# Windows（Docker Desktop 需已启动）
cd C:\D\code\AI-CICD-System
docker compose up -d
```

```bash
# WSL
cd /mnt/c/D/code/AI-CICD-System && docker compose up -d
```

### 2. 启动 supervisor（唯一入口，行为处处一致）

`.env` 由 chronicler/app/config.py **自动加载**（已存在的进程环境变量优先），
无论怎么启动行为都一致；脚本/服务只是同一命令的壳：

```powershell
# Windows（调试：前台跑；常驻：把 scripts\start-chronicler.ps1 加入开机启动项）
chronicler\.venv-win\Scripts\python -m chronicler serve
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
| 配置 | `chronicler/config/*.yaml` 与 `tools.d/*.yaml` 改文件即热生效；`data/chronicler/config/` 同名文件覆盖内置 |
| 服务日志 | 前台终端直接看；后台启动的在 `data/chronicler/supervisor.log` |
| Run 日志 | `data/chronicler/runs/<run_id>/run.log`（或页面「任务」→ 日志） |
| 容器日志 | 首页组件卡片「日志」按钮，或 `docker logs aisystem-<name>-1` |
| 数据库 | `data/chronicler/chronicler.db`（SQLite，可用 `sqlite3` 或 DBeaver 直查） |

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 页面 500 且日志有 UnicodeDecodeError | Windows GBK 解码坑 | 确认代码已含 `encoding="utf-8"` 修复（AGENTS.md 已知环境坑） |
| OIDC 登录 token 交换失败 | 代理拦截 127.0.0.1 | 确认进程走 trust_env=False；shell 里测试用 `curl --noproxy '*'` |
| app.localhost 502 | supervisor 没起或 Caddy 未重载 | 先验 127.0.0.1:8600 直连；再 `docker compose up -d caddy` |
| 改了代码不生效 | 后台旧进程还在 | 停掉 8600 端口的旧进程再启动（Windows：`Get-NetTCPConnection -LocalPort 8600` 找 PID） |
| PyCharm 调试报端口占用 | 后台服务实例占着 8600 | 调试配置加环境变量 `CHRONICLER_PORT=8601` 错开（经 8601 直连调试，不影响正式入口）；或先停服务实例 |
| 容器全部消失 | Docker Desktop 未启动 | 启动 Docker Desktop 后 `docker compose up -d`（restart 策略自动恢复） |

## 回滚（如适用）

调试出问题想回到干净状态：`docker compose restart`（底座）；supervisor 直接 Ctrl+C 重启进程即可，数据都在 `data/chronicler/` 不受影响。
