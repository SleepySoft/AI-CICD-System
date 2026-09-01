# 部署与交付机制

> 版本：v1.1 · 日期：2026-09-01 · 状态：生效
> 定位：环境的交付形态与部署机制（WHY/WHAT 摘要见 ../why/vision.md、../what/environment.md）；操作步骤见 ../runbooks/deploy.md
> 关联需求：NFR-003、NFR-004、NFR-006

## 1. WHY / WHAT 摘要

产品本体是宿主侧 supervisor（Chronicler，ADR-0020/0022），容器栈为可选底座；容器栈事实源是组件目录
`chronicler/components/<name>/`（compose.yml + plugin.yaml，ADR-0027），WSL/VM 镜像只是封装。
服务清单、域名、启停契约、资源分档等见 ../what/environment.md。

## 2. HOW

### 2.1 交付形态

```
仓库根/
├── .env.example            # 全部可调参数（首要依赖：启动前须 cp 为 .env 并编辑 *_change_me）
├── chronicler/             # 产品本体：supervisor（主入口 `python -m chronicler serve`）
│   ├── app/                # FastAPI + SQLite + 组件注册表/生命周期（tools.py）
│   └── components/<name>/  # 组件目录：plugin.yaml + compose.yml（+ SKILL.md/hooks/）
├── images/                 # 各工具链 Dockerfile
└── scripts/                # 构建/接线/验证脚本
    ├── up.sh               # 底座接线（前置校验 .env 与 supervisor 健康；不拉起 supervisor）
    ├── wire-sso.sh / wire-chronicler.sh
    └── verify*.sh / check-kc.sh
```

WSL/VM 封装**复用同一组件定义**，不允许出现独立配置副本（NFR-006）。

### 2.2 启动与接线机制

1. 前置：仓库根 `.env` 存在（`cp .env.example .env` 并编辑所有 `*_change_me`）；主入口 serve 会校验，缺失即提示并退出（ADR-0029）。
2. 启动 supervisor（唯一入口）：`python -m chronicler serve`（或 systemd 用户服务，install-service.sh）；启动钩子按 `plugin.yaml` 的 `autostart` 标记拉起组件（FR-MGR-022），dockerd 未就绪时每 20s 重试至多 10 分钟。
3. 组件拉起：容器存在→`start`；不存在→组件 `hooks/deploy.py`（若提供）否则 `docker compose -p aisystem --env-file <仓库根>/.env -f <组件 compose.yml> up -d`（ADR-0027）；Keycloak 健康端点在 **9000** 端口。
4. 接线脚本完成运行时注册：`wire-sso.sh`（Gitea↔Keycloak + Gitea 管理员）、`wire-chronicler.sh`（可选 OIDC 后端）。
5. 验证脚本冒烟：`verify.sh`（环境）、`verify-chronicler.sh`（supervisor）、`check-kc.sh`（Keycloak）。

### 2.3 启停契约（替代旧 profile 机制）

根 docker-compose.yml 与 profile 已废除（ADR-0027）。启停由组件注册表统一管理：`autostart` 标记决定是否随 supervisor 启动；用户在首页工具面板按需部署/启停非自启组件（admin），普通用户只读。重负载组件（Android 构建、本地模型等）默认不自启（NFR-003）。

### 2.4 安装器（规划）

aisys-installer（Python/Textual TUI + FastAPI 管理页）：环境探测 → 组件勾选 → 域名/端口/管理员/LLM Key 收集 → 分步部署（失败给原因与修复建议，断点续装）→ 冒烟测试 → 打印访问清单。

## 3. 决策与备选

| 决策点 | 选择 | ADR |
|--------|------|-----|
| 运行拓扑 | 宿主侧 supervisor，跟随 dockerd 同环境 | ../adr/0020-manager-out-of-docker-supervisor.md |
| 产品定位 | Chronicler supervisor + 可选底座 | ../adr/0022-product-positioning-chronicler.md |
| 组件形态 | 组件目录自包含 + 钩子契约 | ../adr/0027-component-directory-hooks.md |
| 启动入口 | 主入口 serve 前置校验 .env，缺失即退出；up.sh 只做底座接线 | ../adr/0029-supervisor-single-entry-env-prereq.md |
| 反向代理 | Caddy（自动 HTTPS、配置极简） | 无（无被认真考虑的备选，未达 ADR 阈值） |
