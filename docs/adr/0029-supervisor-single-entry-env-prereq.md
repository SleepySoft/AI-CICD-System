# ADR-0029 supervisor 唯一主入口与 .env 首要依赖前置校验

> 日期：2026-09-01 · 状态：已接受
> 关联：what/environment.md、how/deployment.md、how/manager-architecture.md、runbooks/deploy.md；需求 NFR-004

## 背景

全新部署实测（2026-09-01）：仓库根 `.env` 缺失时，supervisor 的 autostart 钩子对每个自启组件执行
`docker compose --env-file <仓库根>/.env ... up -d`，全部失败但只写入 `audit_log`，界面与常规日志均无提示，
用户看到的现象是"组件没起来且不知道为什么"。同时存在两个启动入口：`scripts/start-chronicler.ps1` 与
`chronicler/__main__.py`，前者硬编码 `chronicler\.venv-win`，venv 路径不符时在后台静默失败，入口行为不一致。

## 决策

`python -m chronicler serve`（chronicler/__main__.py）是 supervisor 唯一启动入口；启动前校验仓库根 `.env`
（首要依赖），缺失即打印创建指引并以退出码 1 退出；删除启动壳脚本，`scripts/up.sh` 不再拉起 supervisor，
只做底座接线并前置校验 `.env` 与 supervisor 健康。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持现状：up.sh 自动 `cp .env.example .env` 并从多个入口启动 | 静默失败不可诊断；双入口行为漂移；自动生成默认凭据掩盖配置缺失 |
| autostart 失败时不退出、仅记录审计表 | 用户无感知，问题延续（本次事故即此路径） |
| 缺 .env 时降级为无底座模式继续运行 | 与"组件应自动拉起"的期望冲突，仍会产生无声的部分可用状态 |
| （中选）主入口前置校验并退出 + autostart 兜底提示 + up.sh 前置校验 | 单入口、失败即报错，修复指引直达 |

## 后果

正面：缺依赖时启动即报错并可诊断；入口唯一、行为一致；up.sh 职责收敛为底座接线。
负面：无底座纯本地账密模式也要求 `.env` 存在（即使 supervisor 自身配置有默认值）。
同步：AGENTS.md、README.md、what/environment.md、how/deployment.md、how/manager-architecture.md、
runbooks/deploy.md、runbooks/dev-debug.md、requirements/stakeholder.md（UR-001）、NFR-004。
