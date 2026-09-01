# Chronicler —— AI 研发任务的史官（supervisor）+ 可选一体化底座

> **产品本体是 `chronicler/`（宿主侧 supervisor 进程）**；可选底座由各组件目录 `chronicler/components/<name>/compose.yml` 定义，supervisor 按需拉起（ADR-0022/0027）。
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
chronicler\.venv-win\Scripts\python.exe -m chronicler serve   # 主入口（唯一启动方式）
```

启动前先在仓库根创建 `.env`（`cp .env.example .env`，编辑所有 `*_change_me`）；serve 会校验，缺失即提示退出。
无底座时直接访问 `http://127.0.0.1:8600`（本地账密登录）。

### 2. 可选底座（compose 栈）

```bash
bash scripts/up.sh            # 底座接线（需 supervisor 已由主入口启动）：校验 .env → 共享网络 → 等核心组件 → SSO 接线 → 冒烟验证（幂等）
bash scripts/wire-chronicler.sh   # 可选：Chronicler 切 Keycloak 统一登录（.env 设 CHRONICLER_AUTH_BACKEND=oidc）
```

底座就绪后 Chronicler 经 `http://app.localhost` 访问（Caddy 回源宿主）。
组件按需部署：首页点「部署」即可（部署定义在各组件目录 `chronicler/components/<name>/compose.yml`，
如 openproject 需求管理、uptime-kuma 监控、ollama 本地模型、browsers、terminal-runtime 沙箱）。

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
│   ├── app/                 # 后端（auth/projects/runner/tools/registry/backup/testing…）+ 前端 static/
│   ├── components/          # 组件目录：一组件一目录（plugin.yaml + SKILL.md + hooks/ + 部署配置）
│   ├── config/              # harness.yaml（agent 命令模板）
│   ├── prompts/             # 内置任务 prompt 模板（版本=内容 hash）
│   └── scripts/             # install-service.sh（systemd 常驻）
├── images/                  # CI 工具链镜像（toolchain-*，非栈组件）
├── docs/                    # 项目文档：requirements/why/what/how/adr/runbooks
├── .agents/skills/          # 项目技能（Agent 行为规范）
├── third_party/             # 外部依赖（git submodule）
└── scripts/                 # up.sh / wire-*.sh / verify*.sh / backup.sh
```

## 备注

- **账号**：有底座时 Keycloak 是唯一账号源（boss 组 = Chronicler admin）；无底座单机用本地账密。详见 `docs/runbooks/deploy.md`。
- **接入 agent**：用户自装 CLI 后在 `chronicler/config/harness.yaml` 登记命令模板即可，见 `docs/runbooks/agent-onboarding.md`。
- **环境坑**（WSL 代理/回收/dockerd 等本机实测）见 `AGENTS.md`「已知环境坑」。
- **授权合规**：组件全部免费含商用；Python 环境用 Miniforge（规避 Anaconda 商用条款）。
