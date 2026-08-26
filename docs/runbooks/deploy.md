# Runbook: 环境部署与初始化

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 适用：WSL2 / Linux，已装 Docker；Windows 下在 WSL 中执行（项目路径 `/mnt/c/D/code/AI-CICD-System`）
> 克隆仓库需 `git clone --recurse-submodules`（ATR 子模块，ADR-0016）
> 关联：scripts/（wire-sso.sh / wire-manager.sh / verify*.sh / build-images.sh）；机制原理见 ../how/deployment.md

## 目的

从全新机器到核心栈可用：compose 启动 → SSO 接线 → Manager 接线 → 冒烟验证全绿。

## 步骤

1. 配置环境变量 — `.env` 存在且无 `*_change_me` 残留
   ```bash
   cp .env.example .env   # 然后编辑，修改所有 *_change_me
   ```
2. 启动核心栈 — 全部 healthy
   ```bash
   docker compose up -d && docker compose ps
   ```
   按需叠加 profile：
   ```bash
   docker compose --profile knowledge --profile monitor up -d
   ```
3. SSO 接线 — Gitea 管理员创建 + Keycloak 登录可用
   ```bash
   bash scripts/wire-sso.sh
   ```
4. Manager 接线 — Keycloak 注册 manager 客户端
   ```bash
   bash scripts/wire-manager.sh
   ```
5. 构建工具链镜像（可选，耗时） — 镜像全部就绪
   ```bash
   bash scripts/build-images.sh    # Windows: scripts\build-images.ps1
   ```
6. 知识库初始化（可选） — vault 推送至 Gitea
   ```bash
   cd knowledge/vault && git init   # 结构规范见 vault README
   ```

## 验证

```bash
bash scripts/verify.sh && bash scripts/verify-manager.sh && bash scripts/check-kc.sh
```

预期输出：三个脚本全部通过；浏览器可访问 http://portal.localhost 且各入口可达（域名清单见 ../what/environment.md）。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| WSL 中 curl 127.0.0.1 被代理拦截（2026-08 实测） | Clash http_proxy | 脚本一律 `curl --noproxy '*'`（权威清单见 AGENTS.md） |
| Keycloak 健康检查失败（2026-08 实测） | 健康端点在 9000 而非 8080 | 用 `http://localhost:9000/health` |
| `docker exec` Gitea CLI 报权限错（2026-08 实测） | Gitea CLI 拒绝 root | `docker exec -u git` |
| 空闲约 60s 后容器全停（2026-08 实测） | WSL2 回收 VM | `.wslconfig` 设 `vmIdleTimeout=-1` |

## 回滚

```bash
docker compose down            # 保留数据（数据在宿主 ${DATA_ROOT:-./data}/ 下，down 不影响）
# 彻底清空：down 后手动删除数据目录（不可恢复，谨慎）
rm -rf "${DATA_ROOT:-./data}"
```
