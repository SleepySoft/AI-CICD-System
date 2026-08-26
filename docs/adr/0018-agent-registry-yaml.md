# ADR-0018 Agent 注册表过渡形态：YAML 注册表 + 锁版本安装脚本

> 日期：2026-08-26 · 状态：已接受
> 关联：what/manager.md（§2.1 agent_profile、§2.2 API）；需求 FR-MGR-002、NFR-002、NFR-008；ADR-0017（本 ADR 是其落地补充，非推翻）

## 背景

ADR-0017 定了 agent 生命周期（CLI 后装持久卷、登录态持久化），但 M1 落地后存在缺口：系统**不知道有哪些 agent**（无注册表、无清单），创建会话靠手填自由文本 command，且 terminal-runtime 镜像内没有任何 agent CLI，手填必然失败。要闭环"注册 → 安装 → 选择拉起"，必须先解决注册表放在哪、安装脚本放哪。

约束：M2 的终态是 Postgres `agent_profile` 表 + `CRUD /api/agents`（what/manager.md §2.1/2.2），但 M1 阶段 Manager 尚无数据库层（requirements.txt 无 DB 驱动）；项目已有 `tools.yaml` 只读挂载热更新的成熟模式。

## 决策

1. **注册表先用 YAML**：`manager/agents.yaml` 为 agent 清单的单一事实源，字段对齐 `agent_profile` 契约（name/cli_type/command/env/api_key_ref/extra_args/max_runtime_sec），只读挂载进 Manager 容器热更新；M2 建 Postgres 层时按同名字段原样迁移，YAML 退役。
2. **安装脚本入仓库**：`scripts/agents/<name>.sh`（锁版本、幂等、写完 `/opt/agents/<name>/VERSION`），只读挂载进 terminal-runtime 容器 `/opt/agent-install/`；安装动作 = Manager `POST /api/agents/{name}/install` 创建 ATR 会话执行脚本，人在 Agent 终端观察进度。
3. **创建会话按注册表解析**：`POST /api/agent/sessions` 增加可选 `agent` 字段，Manager 查注册表覆盖 command 并注入 env（`HOME=/opt/agents/<name>`、PATH、静态 env、`api_key_ref` 从 Manager 环境变量解析）；不指定 agent 时保持自由 command 的原有行为。
4. **terminal-runtime 镜像补 node 底座**（ADR-0017 声明的 node/python/tmux 底座此前缺 node）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 直接落地 Postgres agent_profile + CRUD（M2 提前） | 需引入 ORM/驱动/迁移管理与前端新页面，工作量数倍，打乱 M1→M2 里程碑顺序 |
| CLI 预装进镜像 | ADR-0017 已否决：重建频繁、体积膨胀，登录态仍需落卷 |
| 注册表写进 tools.yaml | tools.yaml 是"环境工具导航"语义（url/容器/健康检查），与 agent 生命周期字段不同域，混入会破坏单一事实源 |
| 安装脚本存持久卷而非仓库 | 脚本是代码不是数据，入仓库才有版本与评审（NFR-009 系统数据 Git 化精神） |

## 后果

- 正面：系统可知 agent 清单与安装状态（`GET /api/agents`）；新增一家 agent = 一段脚本 + 一条 YAML，不动镜像（ADR-0017 约定闭环）；字段与 M2 Postgres 契约同名，迁移零歧义。
- 负面：注册表改内容需改文件重新挂载（YAML 只读挂载天然支持热更新，可接受）；CRUD/连通性自检 `/api/agents/{id}/test` 仍待 M2。
- 同步：what/manager.md §2.1/2.2 注明过渡形态；runbooks/agent-onboarding.md 新增；traceability.md FR-MGR-002 行更新；AGENTS.md 硬性约定补一条。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
