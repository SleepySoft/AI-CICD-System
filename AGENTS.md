# AGENTS.md —— AI-CICD-System 项目上下文

## 项目定位

产品本体是 **Chronicler**（宿主侧 supervisor，ADR-0020/0022）；compose 栈是默认自带的可选底座。两部分：

1. **Chronicler**（`chronicler/`）：宿主侧 Python 进程（FastAPI + SQLite + Vue3 CDN SPA），本地账密鉴权（admin/user），
   工程管理（git 链接）+ harness 登记（命令模板，ADR-0021）+ 任务执行（subprocess 拉起 agent CLI）+ 工具面板。
2. **环境底座**（可选）：Docker Compose 编排 Gitea / Jenkins / Keycloak / Qdrant / Outline / OpenProject 等；
   terminal-runtime/ATR 为 sandbox profile（可选隔离沙箱，ADR-0021）。WSL/VM 镜像是对 Compose 的封装。

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
- `openproject/` —— Agent 操作 OpenProject 的规范：API 认证与 curl 约定、状态流转
  （人提/AI 执行/AI 标记）、`OP#<id>` 提交关联、手工导出配套（ADR-0011/0014）。

新增技能：在 `.agents/skills/` 下建子目录（小写连字符命名），写 SKILL.md
（frontmatter 仅 name/description），并在本节登记一行。

## 硬性约定

- 所有脚本/配置文件统一 **LF 行尾**（.gitattributes 已强制；Windows 编辑后注意转换，
  或运行 `scripts/dev-sync.sh`）。
- **密钥绝不入库**：只提交 `.env.example`；`.env` 已在 .gitignore。
- **数据显式落宿主**（NFR-008/009，ADR-0012/0026）：`data/public/`（组件交换区，挂所有容器）
  与 `data/private/<组件>/`（仅挂载声明者）二分；API 型组件用 private，文件型产物用 public；
  机密永不落 data。禁止命名卷存业务数据；`data/` 已入 .gitignore。
- 组件全部免费（含商用）：Python 环境用 **Miniforge**（禁用 Anaconda/defaults 通道）。
- 新增环境服务/组件：`chronicler/components/<name>/` 一个目录装一切（ADR-0027）——
  `plugin.yaml`（注册：group/desc/url/container/autostart/critical/driver/data）+
  可选 `SKILL.md`（能力注入，ADR-0025）+ 可选 `hooks/backup.py` / `hooks/deploy.py`；
  docker 组件另需 `docker-compose.yml` 服务 + `caddy/Caddyfile` 子域名。
- 新增 agent：用户在宿主自装 harness 后，在 `chronicler/config/harness.yaml` 登记一条命令模板
  （ADR-0021；操作流程见 `docs/runbooks/agent-onboarding.md`）。
- compose 校验：`docker compose config -q`（在 WSL 中执行，项目路径 `/mnt/c/D/code/AI-CICD-System`）。

## 部署/验证

底座（WSL 或 Windows Docker Desktop 均可，ADR-0020“跟随 dockerd 同环境”；本机当前部署在 **Windows Docker Desktop**）：

```bash
bash scripts/up.sh                # 底座一键：起核心栈 → SSO 接线 → 冒烟验证（幂等）
```

supervisor（产品本体，跟随 dockerd 同环境）：

```bash
# WSL/Linux:
python3 -m venv chronicler/.venv && chronicler/.venv/bin/pip install -r chronicler/requirements.txt
chronicler/.venv/bin/python -m chronicler create-admin   # 首次：建管理员
chronicler/.venv/bin/python -m chronicler serve          # 或 bash chronicler/scripts/install-service.sh（systemd）

# Windows（本机当前）：
py -m venv chronicler\.venv-win; chronicler\.venv-win\Scripts\pip install -r chronicler\requirements.txt
powershell -File scripts\start-chronicler.ps1            # 读 .env 后启动（8600）
```

详见 docs/runbooks/deploy.md。

## 已知环境坑（本机实测）

- WSL 有原生 dockerd（docker.socket enabled+active），非常规 Docker Desktop shim（2026-08-27 实测复核）；
  容器常驻使 VM 不易被空闲回收，`.wslconfig` 设 `vmIdleTimeout=-1` 作双保险。
- WSL 中 http_proxy（Clash）会拦截 127.0.0.1 的 curl → 脚本一律 `curl --noproxy '*'`。
- Keycloak 26 健康端点在 **9000** 端口（非 8080）。
- Gitea CLI 拒绝 root：`docker exec -u git`。
- Jenkins 插件 ID 是 `allure-jenkins-plugin`（不是 `allure`）。
- PowerShell 内联 wsl 命令避免 `$()`/`*` 转义问题 → 写成 scripts/*.sh 再执行。
- Windows 侧 Python subprocess 捕获输出必须显式 `encoding="utf-8", errors="replace"`
  （`text=True` 用 GBK 解码，遇 UTF-8 提交信息 stdout 变 None，2026-08-27 实测）。
- Windows 部署时 Docker Desktop 需随登录自启（Settings → General → Start when you sign in），
  否则栈和 SSO 全不可用；supervisor 自启钩子已带 dockerd 就绪重试（10 分钟窗口）兜底启动慢的场景。

## 路线图（Manager）

M2 代码源管理 + harness 执行器（宿主直起，ADR-0021）→ M3 内置任务（code-insight/日报/gap分析/合规/knowhow蒸馏/综合报告）
→ M4 待审闭环 → M5 CI 综合报告 → M6 supervisor Nuitka 保密打包。详见 docs/what/manager.md §里程碑。

## 文档同步债（剩余）

- 仓库名 `AI-CICD-System` 与 Chronicler 新定位不符，更名再议（ADR-0022 记录在案）。
- 文档文件命名仍沿用 manager.md（what/how/functional），随模块更名统一改。
