# 功能需求：环境编排（ENV）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：compose 编排、统一入口、门户与监控的功能需求；规格见 `../../what/environment.md`

### FR-ENV-001 Docker Compose 统一编排
- 状态: 生效 | 上层: UR-001, NFR-006 | 优先级: P0
- 描述: 全部服务由仓库根 `docker-compose.yml` 编排，按 profile（knowledge/requirements/monitor/localai/browsers）分组。
- 验收: `docker compose config -q` 通过；各 profile 可独立叠加启动。

### FR-ENV-002 统一域名入口
- 状态: 生效 | 上层: UR-006 | 优先级: P0
- 描述: 所有 Web 系统经 Caddy 反代以 `*.localhost` 子域名访问。
- 验收: 浏览器访问 git/ci/sso/portal/app 等子域名均可达对应服务。

### FR-ENV-003 统一门户导航
- 状态: 生效 | 上层: UR-006 | 优先级: P1
- 描述: Homepage 门户聚合全部系统入口，按 dev/boss 组显隐。
- 验收: boss 与 dev 登录门户看到的分组不同。

### FR-ENV-004 状态监控
- 状态: 生效 | 上层: NFR-004 | 优先级: P2
- 描述: Uptime Kuma 监控各服务健康状态并告警。
- 验收: 状态页展示核心服务存活；停掉任一服务后出现 down 告警。

### FR-ENV-005 SSO 统一认证
- 状态: 生效 | 上层: UR-006 | 优先级: P0
- 描述: Keycloak 提供 OIDC，预置 realm 与 dev/boss 组；Gitea、Outline、Manager 接入。
- 验收: 一次 Keycloak 登录可进入各子系统；组映射正确。
