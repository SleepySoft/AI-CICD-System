# ADR-0004 SSO 与权限选 Keycloak（OIDC + dev/boss 组）

> 日期：2026-08-21 · 状态：已接受
> 关联：how/sso-wiring.md；需求 FR-ENV-005、BR-008、UR-006
> （本篇为文档重构时对原 docs/01 §3.9 决策的追记）

## 背景

BR-008 要求开发/老板权限区分；Gitea、Jenkins、Outline、OpenProject、Manager 都需要统一认证。各系统均支持 OIDC。

## 决策

选 **Keycloak** 作为统一 SSO：预置 realm（含 dev/boss 组与客户端），token 的 `groups` claim 作为各系统角色映射的统一载体。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 各系统内置账号各自为政 | 无法满足单点登录与统一 RBAC（BR-008） |
| Authentik / Authelia | 功能满足，但团队熟悉度与文档生态不如 Keycloak；无否决性差异，取熟悉度 |
| LDAP 直接集成 | 增加 LDAP 服务运维负担；OIDC 已足够 |

## 后果

- 正面：一次登录全覆盖；组驱动 RBAC 一处定义多处生效。
- 负面：Keycloak 配置复杂（用预置 realm + 接线脚本对冲，见 how/sso-wiring.md）。
- 同步：keycloak/realm/、scripts/wire-sso.sh、scripts/wire-manager.sh。
