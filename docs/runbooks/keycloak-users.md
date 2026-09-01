# Runbook: Keycloak 用户与权限管理

> 版本：v1.0 · 日期：2026-09-01 · 状态：生效
> 适用：可选底座已起（keycloak 组件运行中）；操作者为 Keycloak 管理员（`.env` 的 `KEYCLOAK_ADMIN/KEYCLOAK_ADMIN_PASSWORD`）
> 关联：chronicler/components/keycloak/、scripts/wire-sso.sh、docs/how/sso-wiring.md；需求 FR-ENV-005、UR-006、FR-MGR-017

## 目的

在 Keycloak 中创建/管理用户并按组授予权限：boss 组 = Chronicler admin，其余（dev 等）= user。

## 前置

- keycloak 组件已运行且健康：首页工具面板「管理」分组 → Keycloak 卡片状态=运行中；或 `docker ps` 见 `aisystem-keycloak-1` 为 healthy（健康端点在 9000，启动约 1 分钟）。
- 访问入口二选一：
  - 已登录 Chronicler（admin）：首页「管理」分组 → Keycloak 卡片 →「打开」（该卡片 `visibility=admin`，普通用户不可见）；
  - 或直连 `http://sso.localhost/admin`。
- 登录凭据：`.env` 的 `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`（`.env.example` 默认 admin / admin_change_me，首次部署后应修改）。

## 步骤

1. 打开 Keycloak 管理台并登录，realm 下拉选择 `aisystem`。
2. 添加用户：左侧 Users → Add user → 填 Username（必填）与 Email → Create。
3. 设置密码：进入该用户 → Credentials → Set password → 输入密码，勾选 Temporary（推荐：首次登录须改密）→ Save。
4. 授予权限：进入该用户 → Groups → Join Group → 选择 `boss`（= Chronicler admin）或 `dev`（= 普通 user）→ Join。

## 验证

- 新用户能登录 Keycloak 接入的系统（Gitea/Outline 等，见 ../what/environment.md）。
- Chronicler 侧：仅 OIDC 后端时，新用户首次「通过 Keycloak 统一登录」自动建档并按组映射角色（boss→admin、其余→user）；local 后端下 Chronicler 本地账号独立管理（`python -m chronicler create-admin`），与 Keycloak 用户无关。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 登录页没有「通过 Keycloak 统一登录」按钮 | `.env` 未启用 OIDC 后端（`CHRONICLER_AUTH_BACKEND=local`，默认） | 管理用户无需启用，直连 `sso.localhost/admin` 即可；要 SSO 登录见 deploy.md §二.3（wire-chronicler.sh） |
| 首页没有 Keycloak 卡片 | 当前登录账号非 admin（卡片 `visibility=admin`） | 用 admin 账号登录；或直连 `sso.localhost/admin` |
| sso.localhost 502 / 打不开 | keycloak 未就绪或已停止 | `docker ps` 看 `aisystem-keycloak-1` 状态；`docker logs aisystem-keycloak-1`；首页卡片点「启动」 |

## 回滚（如适用）

删除用户：Users → 选中用户 → 右上角 Delete（不可恢复，谨慎）。误改分组：Groups → Leave Group 后重新 Join。
