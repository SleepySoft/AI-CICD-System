# SSO 接线机制（Keycloak OIDC）

> 版本：v1.2 · 日期：2026-09-07 · 状态：生效
> 定位：统一认证的内部机制；SSO 契约（组、角色映射）见 ../what/environment.md §2.3
> 关联需求：FR-ENV-005、UR-006、BR-008

## 1. WHY / WHAT 摘要

所有子系统统一经 Keycloak OIDC 登录，dev/boss 组驱动各系统的 RBAC（BR-008）。契约见 what/environment.md。

## 2. HOW

### 2.1 realm 预置

`chronicler/components/keycloak/realm/` 下的 realm 配置随容器启动自动导入：预置 `dev`/`boss` 组与测试用户；**不含任何 OIDC 客户端**（密钥不能入库，客户端一律运行时注册）。健康检查走 **9000** 端口（管理端点，非 8080）。

### 2.2 运行时接线

组件各自的 OIDC 客户端由消费方自己的 initialize hook 幂等注册（gitea、outline；
ADR-0027「消费方自负」）。Keycloak 组件另提供通用能力 `hooks/oidc.py`
（`upsert-client <client_id> <secret> <base_url> <callback_path>`，ADR-0047）：
幂等创建/更新客户端（密钥、回调地址），并补建 realm 模板缺失的 profile/email scope
及 claim 映射。Chronicler 自身客户端（核心非组件，无 hook 载体）由管理员显式触发
一次该能力完成接线；核心侧自动联动暂缓。老脚本 `scripts/wire-sso.sh` /
`scripts/wire-chronicler.sh` / `scripts/check-kc.sh` 属待回收脚手架（ADR-0037/0038），
糊化 .env 后已不可直接运行。

### 2.3 角色映射机制

token 的 `groups` claim 是统一的角色载体：Chronicler 后端校验 JWT 取 `groups` 映射 boss→admin、其余→user；Outline 用集合级权限；Gitea 用组织/团队。

### 2.4 已知坑（详见 AGENTS.md）

WSL 中 curl 须 `--noproxy '*'`（Clash 会拦截 127.0.0.1）；Keycloak 26 健康端点在 9000；Gitea CLI 拒绝 root。
