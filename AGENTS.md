# AGENTS.md —— AI-CICD-System 项目上下文

## 项目定位

一体化 AI 研发环境 + 管理服务。两部分：

1. **环境**（本仓库主体）：Docker Compose 是唯一事实源，含 Gitea / Jenkins / Keycloak /
   Qdrant / Outline / OpenProject / MkDocs / Playwright / Ollama / Manager / terminal-runtime。
   WSL/VM 镜像是对 Compose 的封装，不单独维护。
2. **管理服务 Manager**（`manager/`）：FastAPI + Vue3(CDN) SPA，Keycloak OIDC 鉴权，
   工具集中管理（`manager/tools.yaml` 注册表）+ Agent 终端（经 terminal-runtime/ATR 控制子 Agent CLI）。

## 关键文档

- `docs/README.md` —— 文档索引（WHY→WHAT→HOW 分层 + 需求 ID 追溯 + 阅读路径）
- `docs/requirements/` —— 需求库（BR/UR/FR/NFR 带 ID，机器可读事实源）
- `docs/why|what|how/` —— 设计文档三层；决策史在 `docs/adr/`；操作手册在 `docs/runbooks/`
- `docs/01、02` —— 重构前的历史文档（状态：过时，仅供溯源）

## 项目技能（.agents/skills/）

Agent 行为规范的单一事实源，每个技能一个子目录（含 SKILL.md），今后会持续新增：

- `docs-management/` —— 项目文档管理规范：docs/ 按 WHY→WHAT→HOW 分层、按模块分文件，
  requirements/ 纵向需求 ID 体系（BR/UR/FR/NFR）+ 追溯矩阵，ADR 与 runbooks 正交轴。
  **凡是在 docs/ 下新建、修改、拆分文档，必须遵循该技能。**

新增技能：在 `.agents/skills/` 下建子目录（小写连字符命名），写 SKILL.md
（frontmatter 仅 name/description），并在本节登记一行。

## 硬性约定

- 所有脚本/配置文件统一 **LF 行尾**（.gitattributes 已强制；Windows 编辑后注意转换，
  或运行 `scripts/dev-sync.sh`）。
- **密钥绝不入库**：只提交 `.env.example`；`.env` 已在 .gitignore。
- 组件全部免费（含商用）：Python 环境用 **Miniforge**（禁用 Anaconda/defaults 通道）。
- 新增环境服务：改 `docker-compose.yml`（按需挂 profile）+ `caddy/Caddyfile` 子域名 +
  `manager/tools.yaml` 注册 + README 更新。
- compose 校验：`docker compose config -q`（在 WSL 中执行，项目路径 `/mnt/c/D/code/AI-CICD-System`）。

## 部署/验证

```bash
cp .env.example .env           # 修改所有 *_change_me
docker compose up -d           # 核心栈
bash scripts/wire-sso.sh       # Gitea↔Keycloak + Gitea 管理员
bash scripts/wire-manager.sh   # Manager↔Keycloak 客户端
bash scripts/verify.sh && bash scripts/verify-manager.sh
```

## 已知环境坑（本机实测）

- WSL2 空闲约 60s 回收 VM → 容器随重启；建议 `.wslconfig` 设 `vmIdleTimeout=-1`。
- WSL 中 http_proxy（Clash）会拦截 127.0.0.1 的 curl → 脚本一律 `curl --noproxy '*'`。
- Keycloak 26 健康端点在 **9000** 端口（非 8080）。
- Gitea CLI 拒绝 root：`docker exec -u git`。
- Jenkins 插件 ID 是 `allure-jenkins-plugin`（不是 `allure`）。
- PowerShell 内联 wsl 命令避免 `$()`/`*` 转义问题 → 写成 scripts/*.sh 再执行。

## 路线图（Manager）

M2 代码源管理 + agent-runner 执行器 → M3 内置任务（code-insight/日报/gap分析/合规/knowhow蒸馏/综合报告）
→ M4 待审闭环 → M5 CI 综合报告 → M6 Nuitka 保密打包。详见 docs/what/manager.md §里程碑。
