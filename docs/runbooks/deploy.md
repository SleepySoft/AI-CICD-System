# Runbook: 环境部署与初始化

> 版本：v1.3 · 日期：2026-09-03 · 状态：生效
> 适用：Windows / WSL2 / Linux，已装 Docker（可选底座）与 Python 3（supervisor）
> 克隆仓库需 `git clone --recurse-submodules`（ATR 子模块，ADR-0016）
> 关联：scripts/（up.sh / wire-sso.sh / verify*.sh / build-images.sh）、chronicler/scripts/install-service.sh；机制原理见 ../how/deployment.md；架构依据 ADR-0020/0021/0022/0023

## 目的

部署分两段，相互独立（ADR-0022：compose 栈降为可选底座，supervisor 为产品本体）：

1. **compose 底座（可选）**：为没有基础设施的团队提供 Gitea / Jenkins / Keycloak 等一体化环境；已有这些设施的团队可整段跳过。
2. **supervisor（Chronicler，产品本体）**：宿主侧进程，ADR-0020 起移出 Docker；v1 零外部服务依赖即可运行（SQLite + 本地账密，ADR-0023）。

## 一、首次 Web 初始化（推荐）

在仓库根目录执行；首次启动**不需要预先创建 `.env` 或管理员**：

1. 建虚拟环境并安装依赖（WSL/Linux）
   ```bash
   python3 -m venv chronicler/.venv
   chronicler/.venv/bin/pip install -r chronicler/requirements.txt
   ```
2. 启动唯一主入口
   ```bash
   chronicler/.venv/bin/python -m chronicler serve
   ```
   Windows 使用 `chronicler\.venv-win\Scripts\python.exe -m chronicler serve`。控制台会打印仅本机可见、
   带一次性引导码的 `/setup` 地址；不要转发该地址。
3. 在浏览器按八阶段向导完成预检、方案选择、配置、计划确认和部署。端口冲突是阻塞项；Windows 若
   `GITEA_SSH_PORT=2222` 落入系统排除区间，请按“常见问题”修改后重新检测。
4. 完成页出现后重启 Chronicler，使进程级配置生效；此后 `/setup` 仅管理员可访问。

中途关闭页面不会停止部署；重新打开控制台给出的地址可续接。失败后可重试失败步骤，若服务重启导致
尚未落盘的秘密丢失，则返回配置步骤重新输入并生成新计划。只有宿主本地管理员可显式重开引导：

```bash
chronicler/.venv/bin/python -m chronicler setup-recover
```

## 二、旧脚本过渡路径（暂保留）

已有 `.env` 的存量环境仍可使用以下路径；脚本将在 Web 初始化完成全部发布验收后回收：

1. `bash scripts/up.sh`：底座接线、SSO 接线和冒烟验证，不拉起 supervisor。
2. `bash scripts/build-images.sh`（Windows：`scripts\build-images.ps1`）：构建可选工具链镜像。
3. 需要单独切换 OIDC 时可执行：
   ```bash
   bash scripts/wire-chronicler.sh
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
app.localhost 经 Caddy 可达、`DOCKER-SOCK-OK`；各入口可达（域名清单见 ../what/environment.md）。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| WSL 中 curl 127.0.0.1 被代理拦截（2026-08 实测） | Clash http_proxy | 脚本一律 `curl --noproxy '*'`（权威清单见 AGENTS.md） |
| Keycloak 健康检查失败（2026-08 实测） | 健康端点在 9000 而非 8080 | 用 `http://localhost:9000/health` |
| `docker exec` Gitea CLI 报权限错（2026-08 实测） | Gitea CLI 拒绝 root | `docker exec -u git` |
| gitea 容器停在 Created、autostart 报 `ports are not available ... forbidden by its access permissions`（2026-09-01 实测） | Windows 排除端口区间覆盖 `GITEA_SSH_PORT`（本机 2180-2279 含 2222） | `netsh interface ipv4 show excludedportrange protocol=tcp` 查区间；`.env` 改 `GITEA_SSH_PORT` 到区间外，再在首页工具面板「部署」gitea（手动 compose 须显式 `DATA_ROOT=<仓库根>/data`，见 AGENTS.md 已知环境坑） |
| 空闲约 60s 后容器全停（2026-08 实测） | WSL2 回收 VM | `.wslconfig` 设 `vmIdleTimeout=-1` |
| app.localhost 经 Caddy 访问 502 | supervisor 未启动或 Caddy 无 host-gateway | 先确认 `curl --noproxy '*' http://127.0.0.1:8600/api/health` 通；检查 compose 中 caddy 的 `extra_hosts` |
| 已初始化实例启动后进入 repair（2026-09-03） | 初始化关闭记录存在，但仓库根 `.env` 丢失 | 从备份恢复 `.env` 后重启；系统不会自动重开未认证引导入口 |

## 回滚

```bash
# 底座：保留数据（数据在宿主 ${DATA_ROOT:-./data}/ 下，停止不影响）
# 在 Chronicler 首页工具面板停止组件（或 docker stop aisystem-<name>-1）；无根 compose，无 docker compose down
# supervisor：先停服务（若注册了 systemd 用户服务）
systemctl --user stop chronicler && systemctl --user disable chronicler
# 彻底清空（不可恢复，谨慎）：down 后手动删除数据目录与虚拟环境
rm -rf "${DATA_ROOT:-./data}" chronicler/.venv
```
