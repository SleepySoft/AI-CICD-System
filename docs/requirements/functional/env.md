# 功能需求：环境编排（ENV）

> 版本：v1.1 · 日期：2026-09-01 · 状态：生效
> 定位：组件编排、统一入口、门户与监控的功能需求；规格见 `../../what/environment.md`

### FR-ENV-001 Docker Compose 统一编排
- 状态: 生效 | 上层: UR-001, NFR-006 | 优先级: P0
- 描述: 全部服务由组件目录定义（`chronicler/components/<name>/compose.yml` + `plugin.yaml` 注册，ADR-0027）；supervisor 按 `autostart` 标记拉起，或由用户在首页工具面板按需部署。
- 验收: 组件 compose 校验通过（`docker compose --env-file .env -f <组件 compose.yml> config -q`）；autostart 标记的组件随 supervisor 启动自动拉起（FR-MGR-022）。

### FR-ENV-002 统一域名入口
- 状态: 生效 | 上层: UR-006 | 优先级: P0
- 描述: 所有 Web 系统经 Caddy 反代以 `*.localhost` 子域名访问。
- 验收: 浏览器访问 git/ci/sso/app 等子域名均可达对应服务。

### FR-ENV-003 统一门户导航
- 状态: 生效 | 上层: UR-006 | 优先级: P1
- 描述: 统一门户入口集成于 Chronicler 首页（分组卡片 + 实时状态 + 跳转链接，复用 tools 注册表）；独立 Homepage 服务已退役。管理操作（启停）仅 admin；导航入口全员可见。
- 验收: 登录 Chronicler 首页可见全部启用组件入口及实时状态；user 角色无启停按钮。

### FR-ENV-004 状态监控
- 状态: 生效 | 上层: NFR-004 | 优先级: P2
- 描述: Uptime Kuma 监控各服务健康状态并告警。
- 验收: 状态页展示核心服务存活；停掉任一服务后出现 down 告警。

### FR-ENV-005 SSO 统一认证
- 状态: 生效 | 上层: UR-006 | 优先级: P0
- 描述: Keycloak 提供 OIDC，预置 realm 与 dev/boss 组；Gitea、Outline、Manager 接入。
- 验收: 一次 Keycloak 登录可进入各子系统；组映射正确。
