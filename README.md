# AISystem —— AI 研发一体化环境

> 环境部分：**Docker Compose 是唯一事实源**，WSL/VM 镜像后续由其封装。
> 需求分析与选型见 [docs/01-需求分析与选型.md](docs/01-需求分析与选型.md)。

## 快速开始（WSL / Linux）

```bash
cp .env.example .env          # 修改所有 *_change_me
docker compose up -d          # 核心栈：Gitea / Jenkins / Keycloak / 门户
```

按需叠加 profile：

```bash
docker compose --profile knowledge up -d                              # + 知识库(Qdrant/Outline/MkDocs)
docker compose --profile requirements --profile monitor up -d         # + 需求管理 + 状态监控
docker compose --profile browsers up -d                               # + 有头浏览器(noVNC)
docker compose --profile localai up -d                                # + Ollama 本地模型
```

## 访问入口（经 Caddy 统一入口，浏览器直接访问）

| 系统 | 地址 | 默认账号 |
|------|------|---------|
| 统一门户 | http://portal.localhost | - |
| Gitea | http://git.localhost | 先跑 `scripts/wire-sso.sh` 创建管理员 |
| Jenkins | http://ci.localhost | `.env` 的 `JENKINS_ADMIN_ID/PASSWORD` |
| Keycloak | http://sso.localhost/admin | `.env` 的 `KEYCLOAK_ADMIN/PASSWORD` |
| 知识库 Outline | http://kb.localhost | Keycloak 登录（预置 `boss`/`dev` 用户） |
| 文档站 | http://docs.localhost | - |
| 需求管理 | http://req.localhost | 首启创建管理员 |
| 状态监控 | http://status.localhost | 首启创建管理员 |
| 有头浏览器 | http://browser.localhost | - |

> `*.localhost` 在现代浏览器自动解析到 127.0.0.1；若不生效，把子域名写入 hosts（`127.0.0.1 portal.localhost git.localhost ...`）。

## 初始化步骤

1. `docker compose up -d` 启动核心栈，等待 healthy：`docker compose ps`
2. SSO 接线：`bash scripts/wire-sso.sh`（Gitea 管理员 + Keycloak 登录，boss 组自动管理员）
3. 构建工具链镜像：`bash scripts/build-images.sh`（或 Windows 下 `scripts\build-images.ps1`）
4. （可选）知识库初始化：`knowledge/vault` 目录 `git init` 后推送到 Gitea；结构规范见 `knowledge/vault/README.md`
5. （可选）Ollama 模型：`docker exec aisystem-ollama-1 ollama pull bge-m3`

## 目录结构

```
├── docker-compose.yml       # 唯一事实源（profiles: knowledge/requirements/monitor/localai/browsers）
├── .env.example             # 全部可调参数
├── caddy/                   # 统一入口反代
├── postgres/init/           # 共享数据库初始化
├── keycloak/realm/          # 预置 realm（dev/boss 组 + OIDC 客户端）
├── jenkins/                 # Dockerfile + 插件清单 + JCasC
├── homepage/config/         # 门户导航（含 boss 视角分组）
├── mkdocs/                  # Agent 结构化文档站
├── knowledge/vault/         # 知识库（human/ai-inbox/know-how 分区）
├── images/                  # 工具链镜像：cpp / android / node / test-python / browsers
└── scripts/                 # 构建与接线脚本
```

## 管理中心（Manager，M1+ 已实现）

`http://app.localhost` —— FastAPI + Vue3(CDN) SPA，Keycloak OIDC 登录：

- **工具总览**：环境内所有工具的集中面板（分组卡片、运行状态实时探测、跳转链接；boss 可启动/停止/重启容器）。工具清单在 `manager/tools.yaml`，改后重启 manager 生效。
- **Agent 终端**：基于 terminal-runtime-skill（ATR，http://term.localhost/ui）的会话控制台——创建会话（`kimi`/`aider`/`bash` 等任意 CLI）、查看屏幕截图、提交命令/按键。boss 可创建与操作，dev 只读观察。

初始化：`bash scripts/wire-manager.sh`（向 Keycloak 注册 manager 客户端）。
验证：`bash scripts/verify-manager.sh`。

> 说明：M1 阶段无数据库（工具清单读 YAML，会话存于 ATR）；任务框架/调度/报告按 docs/02 设计后续迭代。

## 环境注意事项（本机实测）

1. **WSL 空闲回收**：本机 WSL2 会在最后一个会话退出约 60 秒后关闭 VM，导致全部容器周期性重启。若希望环境常驻，请在 Windows 用户目录的 `C:\Users\<你>\.wslconfig` 中加入：
   ```ini
   [wsl2]
   vmIdleTimeout=-1
   ```
   然后执行 `wsl --shutdown` 重启 WSL 生效。
2. **代理干扰**：WSL 中若设置了 `http_proxy`（如 Clash），对 `127.0.0.1` 的 curl 可能被代理拦截返回 502；验证脚本已用 `--noproxy '*'` 规避。容器间通信不受影响。
3. **WSL 内不解析 `*.localhost`**：在 WSL 里用域名访问需先 `sudo bash scripts/fix-hosts.sh`；Windows 浏览器（Chrome/Edge/Firefox）可直接访问，无需处理。

## 备注

- **Jenkins 构建**：容器挂载了宿主 `docker.sock`，流水线中直接 `docker run aisystem/toolchain-*` 起一次性构建容器。
- **权限模型**：Keycloak 预置 `dev`/`boss` 组；Outline 用集合权限、Gitea 用组织/团队落实"老板可见蒸馏报告与私有 know-how"。
- **授权合规**：Python 环境用 Miniforge（conda-forge），规避 Anaconda 2024 商用收费条款。
- 管理程序（Python 交互安装器 + Web 控制面）为下一阶段，不在本仓库当前范围内。
