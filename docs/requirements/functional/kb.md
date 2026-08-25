# 功能需求：知识库（KB）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：知识库分区、索引与协作的功能需求；规格契约见 `../../what/knowledge.md`

### FR-KB-001 Markdown vault 单一事实源
- 状态: 生效 | 上层: UR-008 | 优先级: P0
- 描述: 知识以 Markdown vault 形式存于 Gitea 仓库，天然版本化、人可读、Agent 可读。
- 验收: 知识条目全部可从 vault 仓库获得；向量库/Web 展示均可由其重建。

### FR-KB-002 来源分区与标注
- 状态: 生效 | 上层: BR-007, UR-008 | 优先级: P0
- 描述: vault 分 `human/`、`ai-inbox/`、`know-how/` 区；条目 frontmatter 含 `origin: human|ai`、`reviewed: bool`。
- 验收: 任一条目可机器判定来源与审核状态；AI 直写仅落在 `ai-inbox/`。

### FR-KB-003 语义检索
- 状态: 生效 | 上层: UR-007 | 优先级: P1
- 描述: Qdrant 对 vault 建语义索引（embedding 默认本地 Ollama bge-m3），供 Agent RAG。
- 验收: 经 MCP 可按语义命中已入库条目；vault 变更后可重建索引。

### FR-KB-004 Web 协作与分级可见
- 状态: 生效 | 上层: UR-004, UR-006 | 优先级: P1
- 描述: Outline 提供 Web 浏览/协作，OIDC 登录 + 集合级权限区分 dev/boss 视图；AI 区只读展示。
- 验收: dev/boss 登录 Outline 可见集合不同。
