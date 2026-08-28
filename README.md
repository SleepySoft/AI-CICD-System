# Chronicler —— AI 研发任务的史官（supervisor）+ 可选一体化底座

> **产品本体是 `chronicler/`（宿主侧 supervisor 进程）**；`docker-compose.yml` 是可一键配齐的可选底座（ADR-0022）。
> 需求与设计文档索引：[docs/README.md](docs/README.md)（WHY→WHAT→HOW 分层 + 需求 ID 追溯）

Chronicler 做什么：登记工程（一个 git 链接）→ 用你自己装好的 agent harness（kimi/claude/aider…）
执行分析任务 → 冻结每次执行的输入快照（Run）→ 产出报告/沉淀经验。顺带管理底座的组件生命周期。

## 快速开始

### 1. supervisor（产品本体，跟随 dockerd 同环境：WSL/Linux 或 Windows）

```bash
# WSL/Linux：
python3 -m venv chronicler/.venv && chronicler/.venv/bin/pip install -r chronicler/requirements.txt
chronicler/.venv/bin/python -m chronicler create-admin   # 首次：建管理员
chronicler/.venv/bin/python -m chronicler serve          # 或 install-service.sh 注册 systemd

# Windows（Docker Desktop 场景）：
py -m venv chronicler\.venv-win; chronicler\.venv-win\Scripts\pip install -r chronicler\requirements.txt
powershell -File scripts\start-chronicler.ps1
```

无底座时直接访问 `http://127.0.0.1:8600`（本地账密登录）。

### 2. 可选底座（compose 栈）

```bash
cp .env.example .env          # 修改所有 *_change_me
bash scripts/up.sh            # 一键：核心栈 + SSO 接线 + 冒烟验证（幂等）
bash scripts/wire-chronicler.sh   # 可选：Chronicler 切 Keycloak 统一登录（.env 设 CHRONICLER_AUTH_BACKEND=oidc）
```

底座就绪后 Chronicler 经 `http://app.localhost` 访问（Caddy 回源宿主）。按需叠加 profile：
`knowledge`（知识库）/ `requirements`（需求管理）/ `monitor` / `localai` / `browsers` / `sandbox`（ATR 隔离沙箱）。

## 访问入口

| 系统 | 地址 | 认证 |
|------|------|------|
| **Chronicler**（首页=统一门户） | http://app.localhost | Keycloak 统一登录（或本地账密兜底） |
| Gitea | http://git.localhost | Keycloak |
| Keycloak 管理台 | http://sso.localhost/admin | `.env` 的 `KEYCLOAK_ADMIN/PASSWORD` |
| Jenkins | http://ci.localhost | 独立账号（`.env`） |
| 知识库 Outline | http://kb.localhost | Keycloak（knowledge profile） |
| 需求管理 | http://req.localhost | 独立账号（requirements profile） |

> `*.localhost` 在现代浏览器自动解析到 127.0.0.1；WSL 内访问需 `sudo bash scripts/fix-hosts.sh`。

## 目录结构

```
├── chronicler/              # 产品本体：宿主侧 supervisor（FastAPI + SQLite + Vue3 SPA）
│   ├── app/                 # 后端（auth/projects/runner/tools/registry…）+ 前端 static/
│   ├── config/              # harness.yaml（agent 命令模板）、components.yaml、tools.d/（组件插件）
│   ├── prompts/             # 内置任务 prompt 模板（版本=内容 hash）
│   └── scripts/             # install-service.sh（systemd 常驻）
├── docker-compose.yml       # 可选底座编排（profiles: knowledge/requirements/monitor/localai/browsers/sandbox）
├── caddy/                   # 统一入口反代（app.localhost → 宿主 8600）
├── keycloak/realm/          # 预置 realm（dev/boss 组 + OIDC 客户端 + scope）
├── jenkins/                 # Dockerfile + 插件清单 + JCasC
├── images/                  # 工具链镜像：cpp / android / node / test-python / browsers / terminal-runtime
├── knowledge/vault/         # 知识库（human/ai-inbox/know-how 分区）
├── docs/                    # 项目文档：requirements/why/what/how/adr/runbooks
├── .agents/skills/          # 项目技能（Agent 行为规范）
└── scripts/                 # up.sh / wire-*.sh / verify*.sh / backup.sh
```

## 备注

- **账号**：有底座时 Keycloak 是唯一账号源（boss 组 = Chronicler admin）；无底座单机用本地账密。详见 `docs/runbooks/deploy.md`。
- **接入 agent**：用户自装 CLI 后在 `chronicler/config/harness.yaml` 登记命令模板即可，见 `docs/runbooks/agent-onboarding.md`。
- **环境坑**（WSL 代理/回收/dockerd 等本机实测）见 `AGENTS.md`「已知环境坑」。
- **授权合规**：组件全部免费含商用；Python 环境用 Miniforge（规避 Anaconda 商用条款）。
