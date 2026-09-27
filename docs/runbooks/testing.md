# Runbook: 组件测试（沙箱 / 巡检 / 漂移审计）

> 版本：v1.1 · 日期：2026-09-27 · 状态：生效
> 适用：Windows 或 WSL，dockerd 可用；生产巡检要求栈已部署
> 关联：机制原理 [how/sandbox-testing.md](../how/sandbox-testing.md)；决策 [ADR-0048](../adr/0048-sandbox-isolated-testing.md)；
> 脚本：scripts/verify-auth.py、scripts/audit-secret-drift.py、scripts/verify-pages.py

## 目的

验证组件"能起、入口通、能登录"，三个层次各一条命令；全部现拉现建现测现毁，不影响生产。

## 步骤

1. **沙箱全量**（CI 同款，验证代码副本）——默认启用组件；加 `--include-disabled` 连
   openproject/outline 一起测：
   ```powershell
   chronicler\.venv-win\Scripts\python.exe -m chronicler sandbox
   ```
   预期输出：`N/N 通过`，退出码 0。常用选项：`--components gitea keycloak`（单点）、
   `--skip-pull`（镜像已在本地时省时）、`--keep --workdir .sandbox-debug`（保留现场调试）、
   `--junit report.xml`（CI 归档）、`SANDBOX_DEBUG=1`（打印 compose 渲染结果）。
2. **生产登录巡检**（验证部署中的系统，SSO 全链路真登录）：
   ```powershell
   chronicler\.venv-win\Scripts\python.exe scripts\verify-auth.py
   ```
   预期：`通过 N，失败 0`；未运行组件列 SKIP 属正常。
3. **秘密漂移审计**（容器 env vs 秘密库，只读）：
   ```powershell
   chronicler\.venv-win\Scripts\python.exe scripts\audit-secret-drift.py
   ```
   预期：全部 `一致`；有 `漂移!` 时按 [runbooks/vault.md](vault.md) 的登录故障排查三步法处置。

## 验证

- 沙箱：结尾 `===== 沙箱可达性结果 =====` 全 PASS 且无残留——
  `docker ps -a --filter name=chronicle-sandbox` 应为空。
- 生产无损确认：沙箱运行期间 `docker ps --format "{{.Names}} {{.Status}}" | findstr aisystem`
  的生产容器状态与启动时间不变。

## 任务链路回归

使用临时 SQLite 与工作区运行接收、重复请求、慢请求、排队与锁保护测试，不启动真实 agent：

```powershell
chronicler\.venv-win\Scripts\python.exe -m unittest chronicler.tests.test_task_lifecycle chronicler.tests.test_change_detection chronicler.tests.test_runtime_profile chronicler.tests.test_projects_sync chronicler.tests.test_oidc_navigation -v
```

前端异步回归脚本为 `chronicler/tests/frontend_lifecycle.js`，可用 Node 执行：

```powershell
node -e "require('./chronicler/tests/frontend_lifecycle.js')(require('fs').readFileSync('chronicler/app/static/app.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1})"
```

生产巡检的 Docker 状态查询失败属于检查失败；不能将权限不足当成「组件未运行」而跳过。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 沙箱 caddy 绑到生产 80 端口 | 父进程环境泄漏生产 .env（compose 进程环境 > --env-file） | 更新到含环境清洗的版本；2026-09-15 已修 |
| down 后报端口占用（WinError 10048） | Docker Desktop 端口代理延迟释放 | 等几秒重试，或 `--http-port` 换端口 |
| 探针 502 但生产组件正常 | httpx/脚本走了系统代理（Clash）劫持 127.0.0.1 | 用项目脚本（已 trust_env=False）；curl 加 `--noproxy '*'` |
| openproject 首启即退 | 上游镜像 zh-CN 首 seed bug | 已由组件 plugin.yaml `sandbox.env` 自述兑过，勿手删 |
| CI 沙箱 stage 报 key.pem | ci-agent 镜像缺 compose 插件的历史报错形态（帮助文本误导） | 重建 ci-agent（已内置 compose v5） |

## 回滚

沙箱异常中断残留容器：手动清理——
`docker ps -aq --filter "label=com.docker.compose.project=chronicle-sandbox" | %{ docker rm -f $_ }`，
再 `docker network rm chronicle-sandbox_default`。生产栈不受沙箱影响，无需回滚。
