# SSO 接线机制（Keycloak OIDC）

> 版本：v1.1 · 日期：2026-09-01 · 状态：生效
> 定位：统一认证的内部机制；SSO 契约（组、角色映射）见 ../what/environment.md §2.3
> 关联需求：FR-ENV-005、UR-006、BR-008

## 1. WHY / WHAT 摘要

所有子系统统一经 Keycloak OIDC 登录，dev/boss 组驱动各系统的 RBAC（BR-008）。契约见 what/environment.md。

## 2. HOW

### 2.1 realm 预置

`chronicler/components/keycloak/realm/` 下的 realm 配置随容器启动自动导入：预置 `dev`/`boss` 组、各子系统 OIDC 客户端、测试用户。健康检查走 **9000** 端口（管理端点，非 8080）。

### 2.2 运行时接线

部分客户端密钥必须在运行时生成并回写，由脚本完成：

- `scripts/wire-sso.sh`：创建 Gitea 管理员（Gitea CLI 拒绝 root，须 `docker exec -u git`）+ 注册 Gitea 的 Keycloak 登录源，boss 组自动管理员。
- `scripts/wire-chronicler.sh`：向 Keycloak 注册 Chronicler 客户端（可选 OIDC 后端，ADR-0023）。
- `scripts/check-kc.sh`：验证 realm 导入与端点可用性。

### 2.3 角色映射机制

token 的 `groups` claim 是统一的角色载体：Chronicler 后端校验 JWT 取 `groups` 映射 boss→admin、其余→user；Outline 用集合级权限；Gitea 用组织/团队。

### 2.4 已知坑（详见 AGENTS.md）

WSL 中 curl 须 `--noproxy '*'`（Clash 会拦截 127.0.0.1）；Keycloak 26 健康端点在 9000；Gitea CLI 拒绝 root。
