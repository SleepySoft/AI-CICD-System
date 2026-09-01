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
- **数据显式落宿主**（NFR-008/009，ADR-0012/0026）：三层——`data/public/`（组件交换区，挂所有容器）、
  `data/private/<组件>/`（仅挂载声明者）、`data/workspace/`（工作区，工程克隆等可由 git 重建，不进备份）；
  机密永不落 data。禁止命名卷存业务数据；`data/` 已入 .gitignore。
- 工程仓库地址只允许远端（Gitea 自托管或 GitHub 等第三方）；本地路径形态不存在——本地的是
  工作空间克隆（`data/workspace/repos/<id>/`）。
- 组件全部免费（含商用）：Python 环境用 **Miniforge**（禁用 Anaconda/defaults 通道）。
- 新增环境服务/组件：`chronicler/components/<name>/` 一个目录装一切（ADR-0027）——
  `plugin.yaml`（注册：group/desc/url/container/autostart/critical/driver/data）+
  可选 `SKILL.md`（能力注入，ADR-0025）+ 可选 `hooks/backup.py` / `hooks/deploy.py`；
  docker 组件另需 `compose.yml` 服务 + `caddy/Caddyfile` 子域名。
- 新增 agent：用户在宿主自装 harness 后，在 `chronicler/config/harness.yaml` 登记一条命令模板
  （ADR-0021；操作流程见 `docs/runbooks/agent-onboarding.md`）。
- 组件 compose 校验：`docker compose --env-file .env -f chronicler/components/<name>/compose.yml config -q`（在 WSL 中执行，项目路径 `/mnt/c/D/code/AI-CICD-System`）。

## 部署/验证

底座（WSL 或 Windows Docker Desktop 均可，ADR-0020“跟随 dockerd 同环境”；本机当前部署在 **Windows Docker Desktop**）：

```bash
bash scripts/up.sh                # 底座接线（需 supervisor 已由主入口启动）：校验 .env → 共享网络 → 等核心组件 → SSO 接线 → 验证
```

底座编排：无根 docker-compose.yml（已废除，ADR-0027）；组件部署定义在各组件目录
`chronicler/components/<name>/compose.yml`，由 supervisor 按需拉起。日常不需手动 compose。

supervisor（产品本体，跟随 dockerd 同环境）：

```bash
# WSL/Linux:
python3 -m venv chronicler/.venv && chronicler/.venv/bin/pip install -r chronicler/requirements.txt
chronicler/.venv/bin/python -m chronicler create-admin   # 首次：建管理员
chronicler/.venv/bin/python -m chronicler serve          # 或 bash chronicler/scripts/install-service.sh（systemd）

# Windows（本机当前）：
py -m venv chronicler\.venv-win; chronicler\.venv-win\Scripts\pip install -r chronicler\requirements.txt
chronicler\.venv-win\Scripts\python.exe -m chronicler serve   # 主入口（唯一启动方式；缺 .env 提示退出，监听 8600）
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
- Gitea webhook 投递后 Jenkins gitea 插件按 URL 匹配任务，内外网域名不一致会静默不触发；
  且 Docker 容器内 *.localhost 按 RFC6761 强制回环（extra_hosts 也难覆盖）→ SCM 源用内网名
  （http://gitea:3000）+ 多分支任务加 PeriodicFolderTrigger 兑底（本机实测，2026-08-29）。
- Jenkins API 的 POST 需要 crumb+cookie jar；URL 含 `[]` 要加 `curl -g`；JCasC jobs 脚本写错会导致 Jenkins 崩溃循环（RestartCount 飚升）——看 `docker logs` 的 InitReactorRunner 错误。
- Windows 本机 `*.localhost` 可能被代理 fake-ip/DNS 劫持 → 用 `scripts/fix-hosts.ps1`（需管理员）
  把子域名钉到 127.0.0.1；写 hosts 用 `[System.IO.File]::AppendAllText`（Add-Content 预读编码会报“流不可读”）。
- Windows Docker 下端口若落入 Hyper-V/WSL 排除区间（本机 2180-2279 覆盖 2222），容器 start 报
  `ports are not available ... forbidden by its access permissions`，但 netstat 看不到任何占用 →
  用 `netsh interface ipv4 show excludedportrange protocol=tcp` 查区间，把 `.env` 对应端口
  （如 `GITEA_SSH_PORT`）改到区间外（本机实测，2026-09-01）。
- 手动 `docker compose --env-file .env -f chronicler/components/<name>/compose.yml` 时，`.env` 的
  `DATA_ROOT=./data` 按 **compose 文件所在目录**解析 → 数据会落入组件目录（`chronicler/components/<name>/data/`）。
  手动操作须显式 `DATA_ROOT=<仓库根>/data`（或走首页工具面板「部署」，supervisor 注入绝对路径）（本机实测，2026-09-01）。
- Windows 侧 Python subprocess 捕获输出必须显式 `encoding="utf-8", errors="replace"`
  （`text=True` 用 GBK 解码，遇 UTF-8 提交信息 stdout 变 None，2026-08-27 实测）。
- Windows 部署时 Docker Desktop 需随登录自启（Settings → General → Start when you sign in），
  否则栈和 SSO 全不可用；supervisor 自启钩子已带 dockerd 就绪重试（10 分钟窗口）兜底启动慢的场景。
- Clash Verge（本机实测，2026-09-01）：TUN 开关开着但 Wintun 网卡可能 Disconnected（核心以 sidecar
  模式启动、非管理员 → TUN 未接管 L3）；出站模式实际可能仍是 rule；PowerShell 会话默认无
  HTTP_PROXY/HTTPS_PROXY → curl/pip/git/codex 等直连被墙（developers.openai.com 403）。
  处置见 docs/runbooks/proxy-clash.md；设代理 env 时 NO_PROXY 必须含内网段
  （10.*、192.168.*、172.16-31.*、*.localhost）。
- 前端资源已本地化（chronicler/app/static/vendor/，vue/element-plus/icons 版本钉死）：
  勿改回 CDN 引用（公司网络/代理下 unpkg 加载不稳，曾实测登录页渲染原始 {{ }}、
  图标按钮不可见但可点，2026-09-01）。图标按钮依赖 app.js 全局注册 ElementPlusIconsVue。

## 路线图（Manager）

M2 代码源管理 + harness 执行器（宿主直起，ADR-0021）→ M3 内置任务（code-insight/日报/gap分析/合规/knowhow蒸馏/综合报告）
→ M4 待审闭环 → M5 CI 综合报告 → M6 supervisor Nuitka 保密打包。详见 docs/what/manager.md §里程碑。

## 文档同步债（剩余）

- 仓库名 `AI-CICD-System` 与 Chronicler 新定位不符，更名再议（ADR-0022 记录在案）。
- 文档文件命名仍沿用 manager.md（what/how/functional），随模块更名统一改。
