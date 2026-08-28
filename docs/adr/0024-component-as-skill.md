# ADR-0024 组件即 SKILL：渐进披露的资源能力注入模型

> 日期：2026-08-27 · 状态：已接受
> 关联：what/manager.md（agent_profile / 任务框架）；需求 FR-MGR-015、FR-MGR-016、FR-MGR-021、FR-MGR-022；ADR-0021（harness 登记）、ADR-0022（底座可选）；本项目 .agents/skills/ 既有规范

## 背景

ADR-0022 将 compose 栈降级为"可选底座"后，系统**无法预知部署环境有哪些组件**（不同用户启用的 profile 不同，甚至全部缺席）。同时 FR-MGR-015 已要求"任务 prompt 只注入已配置资源的访问说明"，但其形态仅为一段扁平文本。设计讨论中确立的目标：组件接入能力应标准化为 SKILL——**有什么组件就有什么 SKILL**，SKILL 下放到组件层，系统与组件完全解耦。

决策时刻已知的约束与问题（讨论中逐条确认）：

- 组件数量不定：prompt 全量注入组件说明会随组件数线性膨胀，agent 注意力被稀释（"组件过多会不会乱"）。
- 相似组件并存（如多个 git 托管）：需要消歧机制，但不能依赖硬编码优先级。
- prompt 模板编写时组件集合未知：模板若指名具体组件必然悬空。
- 资源形态不一：HTTP API 组件（gitea/outline）与文件目录资源（shadow 库、文档 vault）需要同一框架承载。
- 已有可复用资产：`.agents/skills/` 的 SKILL.md 规范（frontmatter name/description + 正文 + references）；`tools.d/` 组件插件注册（ADR-0022 后）；prompt 的 `{{components}}` 占位符（v1 已落地扁平注入）。

## 决策

1. **渐进披露三层注入**：
   - L0 摘要（始终注入 prompt）：组件 name + 一句话描述（含"何时用它"），每个组件一行，按 group 分区排版；
   - L1 SKILL.md 正文（agent 按需自取）：prompt 只注入文件路径，agent 决定使用某组件后自行读取；
   - L2 references/（SKILL.md 内引用的冷门细节：API 细节、示例），不进 prompt。
2. **组件 = 一对文件**：`chronicler/config/tools.d/<name>.yaml`（注册与生命周期，已有）+ `chronicler/skills/<name>/SKILL.md`（能力描述，新增），同名关联；增删组件 = 增删一对文件，系统零改动。
3. **SKILL.md 四要素模板**：能干什么（capabilities）/ 不能干什么（boundaries）/ 怎么访问（路径+凭据引用）/ 何时选我而非别人（消歧）。
4. **资源形态同构**：`driver` 字段区分 docker | api | file；文件类资源（如 shadow 库）作为同层组件注册，SKILL.md 中描述目录结构契约与读写规则——不是 SKILL 的"下一层"。
5. **prompt 纪律**：模板只对能力类别说话、永不指名组件（"若资源区提供 git 托管 API 则…未提供则降级"）；组件集合在运行时注入。
6. **消歧三手段**：SKILL 描述写差异 → 注册表 `default: true` 标同类首选 → 兜底由 agent 在产出中注明选择理由。
7. **规模兜底**：组件数量真到膨胀时，任务策略（FR-MGR-021）可加 tag 白名单过滤注入范围（预留，本次不实现）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 全量注入（组件说明全文进 prompt） | 上下文成本随组件数线性膨胀；组件一多 agent 必乱 |
| 维持扁平文本注入（FR-MGR-015 现状） | 能力描述无结构、无深度，复杂组件（多 API/多目录规则）说不清 |
| 组件能力走 MCP server 注册 | MCP 是工具调用协议，适合固定工具集；组件按需启停、形态不定，MCP 引入额外进程管理负担，且 harness 各家对 MCP 支持不一 |
| 相似组件用优先级数字排序 | 硬编码优先级在跨环境部署时必然失真；描述消歧 + default 标记更诚实 |

## 后果

- 正面：系统与组件彻底解耦（组件增删零系统改动）；prompt 上下文成本恒定；SKILL.md 可独立演进、可评审、可复用到其它 agent 体系；与 .agents/skills/ 规范同源，心智模型统一。
- 负面：能力描述质量依赖 SKILL.md 写作水平（靠模板与评审约束）；agent 多一次"读文件"动作（harness 需具备读文件能力——主流 CLI 都具备）；L0 摘要与 SKILL.md 正文存在双写一致性风险（摘要由 loader 从 frontmatter 提取可缓解）。
- 待办（随深入讨论细化后实现）：runner.py prompt 组装改为 L0 摘要 + 路径注入；chronicler/skills/ 目录与首批组件 SKILL.md（gitea/keycloak 等 5 个示范）；FR-MGR-015 描述升级为三层模型；组件 loader 校验 SKILL.md 存在性与 frontmatter 合法性。
- 开放问题（下轮讨论）：SKILL.md 是否允许引用组件外共享片段（避免重复）；任务策略 tag 白名单的 schema；shadow 库等 file 类组件的写入审批流与 SKILL 的边界表述。
- 同步：docs/README.md 索引登记本篇；落地时再改 what/manager.md §任务类型框架与 traceability.md FR-MGR-015。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
