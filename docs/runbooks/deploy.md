# Runbook: 环境部署与初始化

> 版本：v1.1 · 日期：2026-08-27 · 状态：生效
> 适用：WSL2 / Linux，已装 Docker（底座）与 Python 3（supervisor）；Windows 下在 WSL 中执行（项目路径 `/mnt/c/D/code/AI-CICD-System`）
> 克隆仓库需 `git clone --recurse-submodules`（ATR 子模块，ADR-0016）
> 关联：scripts/（up.sh / wire-sso.sh / verify*.sh / build-images.sh）、chronicler/scripts/install-service.sh；机制原理见 ../how/deployment.md；架构依据 ADR-0020/0021/0022/0023

## 目的

部署分两段，相互独立（ADR-0022：compose 栈降为可选底座，supervisor 为产品本体）：

1. **compose 底座（可选）**：为没有基础设施的团队提供 Gitea / Jenkins / Keycloak 等一体化环境；已有这些设施的团队可整段跳过。
2. **supervisor（Chronicler，产品本体）**：宿主侧进程，ADR-0020 起移出 Docker；v1 零外部服务依赖即可运行（SQLite + 本地账密，ADR-0023）。

## 一、compose 底座（可选）

1. 配置环境变量 — `.env` 存在且无 `*_change_me` 残留
   ```bash
   cp .env.example .env   # 然后编辑，修改所有 *_change_me
   ```
2. 一键起栈 — 起核心栈 → SSO 接线 → 冒烟验证（幂等，可反复执行）
   ```bash
   bash scripts/up.sh
   ```
   up.sh 只管 compose 栈 + wire-sso + 验证，**不拉起 supervisor**。按需叠加 profile：
   ```bash
   docker compose --profile knowledge --profile monitor up -d
   docker compose --profile sandbox up -d    # ATR 可选隔离沙箱（ADR-0021）
   ```
3. 构建工具链镜像（可选，耗时） — 镜像全部就绪
   ```bash
   bash scripts/build-images.sh    # Windows: scripts\build-images.ps1
   ```

## 二、supervisor（Chronicler，产品本体）

在仓库根目录执行（WSL）：

1. 建虚拟环境并安装依赖
   ```bash
   python3 -m venv chronicler/.venv
   chronicler/.venv/bin/pip install -r chronicler/requirements.txt
   ```
2. 创建管理员 — 本地账密（admin/user 两角色；鉴权后端可插拔，ADR-0023）
   ```bash
   chronicler/.venv/bin/python -m chronicler create-admin
   ```
3. （可选）切换统一认证 — 底座含 Keycloak 时，用 OIDC 后端实现一次登录全站通：
   ```bash
   # .env 中设 CHRONICLER_AUTH_BACKEND=oidc 与 CHRONICLER_OIDC_SECRET，然后：
   bash scripts/wire-chronicler.sh   # 在 Keycloak 创建 chronicler 客户端（幂等）
   ```
   重启 supervisor 后登录页出现「经 Keycloak 统一登录」；groups 映射 boss→admin、其余→user，
   首次登录自动建档。Gitea/Outline 与 Chronicler 共享 Keycloak 会话，无需重复登录。
4. 启动（二选一） — 监听 8600
   ```bash
   chronicler/.venv/bin/python -m chronicler serve   # 前台运行
   bash chronicler/scripts/install-service.sh         # 或注册 systemd 用户服务常驻
   ```

访问入口：无底座时直连 http://127.0.0.1:8600 ；两段并存时经 Caddy 访问
http://app.localhost （Caddy 已反代到 host.docker.internal:8600，caddy 服务带
`extra_hosts: host-gateway`）。

## 验证

```bash
bash scripts/verify-chronicler.sh                    # supervisor 冒烟（直连 + 经 Caddy + 401 检查）
bash scripts/verify.sh && bash scripts/check-kc.sh   # 底座冒烟（仅在部署了底座时）
```

预期输出：verify-chronicler.sh 中 `/api/health` 返回 200、未登录访问受保护 API 返回 401、
app.localhost 经 Caddy 可达、`DOCKER-SOCK-OK`；底座侧浏览器可访问 http://portal.localhost
且各入口可达（域名清单见 ../what/environment.md）。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| WSL 中 curl 127.0.0.1 被代理拦截（2026-08 实测） | Clash http_proxy | 脚本一律 `curl --noproxy '*'`（权威清单见 AGENTS.md） |
| Keycloak 健康检查失败（2026-08 实测） | 健康端点在 9000 而非 8080 | 用 `http://localhost:9000/health` |
| `docker exec` Gitea CLI 报权限错（2026-08 实测） | Gitea CLI 拒绝 root | `docker exec -u git` |
| 空闲约 60s 后容器全停（2026-08 实测） | WSL2 回收 VM | `.wslconfig` 设 `vmIdleTimeout=-1` |
| app.localhost 经 Caddy 访问 502 | supervisor 未启动或 Caddy 无 host-gateway | 先确认 `curl --noproxy '*' http://127.0.0.1:8600/api/health` 通；检查 compose 中 caddy 的 `extra_hosts` |

## 回滚

```bash
# 底座：保留数据（数据在宿主 ${DATA_ROOT:-./data}/ 下，down 不影响）
docker compose down
# supervisor：先停服务（若注册了 systemd 用户服务）
systemctl --user stop chronicler && systemctl --user disable chronicler
# 彻底清空（不可恢复，谨慎）：down 后手动删除数据目录与虚拟环境
rm -rf "${DATA_ROOT:-./data}" chronicler/.venv
```
