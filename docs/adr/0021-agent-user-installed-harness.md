# ADR-0021 Agent 执行模型：用户自装 harness + 配置登记 + 尽力持久会话（部分推翻 ADR-0017）

> 日期：2026-08-27 · 状态：已接受
> 关联：what/manager.md（agent_profile、Agent 终端）；需求 FR-MGR-002、NFR-002、NFR-008；ADR-0016、ADR-0017（被部分推翻）、ADR-0020（前提）

## 背景

ADR-0020 将 Manager 移出容器为宿主侧 supervisor，与代码/文档资产同侧。ADR-0017 的 agent 模型（CLI 后装进 terminal-runtime 持久卷、容器内执行）建立在"agent 必须容器化以避宿主污染/密钥扩散"的假设上，决策时刻已知的新约束：

- supervisor 要给 agent 提供**真实宿主路径**供其分析代码/文档资产；agent 在容器内则路径翻译问题回归，0020 的收益被抵消。
- 用户宿主上往往**已安装并登录**各家 agent harness（kimi / claude / codex / pi …）；要求容器内再装一份 = 双份安装、双份登录态、双份版本漂移。
- 各家 harness 命令行能力差异大：有的支持持久/恢复会话，有的仅一次性会话；supervisor 真正需要知道的只是"调哪个 agent、命令与参数是什么"（如 `--yolo`）。
- ADR-0017 仍成立的部分：登录态持久化复用、endpoint 抽象（`base_url` + key）、不内置各家登录流程。

## 决策

**agent 执行位置改为 supervisor 所在宿主，由用户自行安装与配置**；supervisor 的 agent 注册表只登记 harness 条目：名称 → 可执行命令 + 参数模板（含 yolo 类开关），不再接管安装与版本锁定。会话管理经 ATR 抽象层**尽力持久**：harness 支持则维持长会话保持上下文；不支持则一次性会话，下次 resume 旧会话后再提交新内容（具体语义 TBD）。terminal-runtime/ATR 容器保留为**可选隔离沙箱**（CI / 不可信任务场景），其去留随 M2/M3 重评。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持 ADR-0017（agent 全容器化） | 路径翻译抵消 0020 收益；与用户已装已登录的现实冲突，双份维护 |
| supervisor 在宿主、agent 仍经 ATR 容器执行 | 路径问题依旧；仅把 0019 的跨界调用换成 HTTP，未解决根本 |
| 立即废弃 terminal-runtime/ATR | CI 与不可信任务的隔离执行无处安放；会话抽象层仍有价值 |

## 后果

- 正面：真实路径零翻译；用户已有安装与登录态直接复用；新增一家 agent = 一条注册表配置，连安装脚本都不再需要；supervisor 对 harness 的掌控面收敛为"命令模板 + 会话抽象"。
- 负面：ADR-0017 防宿主污染/密钥扩散的收益转由用户自管（agent 是用户自己装的，责任边界随之转移）；`agents.yaml` 契约变更（从"安装脚本 + 版本锁定"改为"命令模板"）；`scripts/agents/*.sh` 锁版本安装脚本降级为可选沙箱（terminal-runtime）专用；宿主上 agent 版本漂移不再受控。
- 待办：agents.yaml 新契约设计（harness 条目 + 参数模板 + 会话能力声明）；ATR 会话抽象从容器服务改造为 supervisor 内模块（持久/resume 语义 TBD）；terminal-runtime 保留为可选 compose profile。
- 同步：ADR-0017 状态标注部分被本篇推翻；what/manager.md agent_profile 契约改写；how/manager-architecture.md §2.3 执行管线改写；requirements/functional/manager.md（FR-MGR-002 周边）、traceability.md、runbooks/agent-onboarding.md、docs/README.md 索引。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
