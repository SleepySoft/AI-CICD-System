# 知识库规格（vault 分区 / frontmatter / 索引契约）

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：知识库对外可见的结构与协作契约；索引重建等机制见各组件配置
> 关联需求：FR-KB-001 ~ FR-KB-004、BR-007

## 1. WHY

知识需要在人（Obsidian 编辑）与 Agent（RAG 检索、蒸馏写入）之间共享，且人工与 AI 产出必须可区分（BR-007）。Markdown vault 是唯一事实源，Qdrant/Outline 都是可重建的派生层。

## 2. WHAT

### 2.1 分区规范（FR-KB-002）

```
knowledge/vault/
├── human/       # 人工笔记（唯一允许人工直写的区）
├── ai-inbox/    # AI 产出待审区（Agent 唯一允许直写的区）
└── know-how/    # 人审通过的 AI 知识卡片（转正区）
```

流转规则：`ai-inbox/` →（人工 approve）→ `know-how/`；reject → 归档不转正。

### 2.2 frontmatter 契约

每个条目必须带：

```yaml
---
origin: human | ai
reviewed: true | false
---
```

Agent 写入 `origin: ai, reviewed: false`；转正时置 `reviewed: true`。

### 2.3 索引契约（FR-KB-003）

- Qdrant 对 vault 建语义索引；embedding 默认本地 Ollama `bge-m3`。
- 索引必须可从 vault 全量重建；vault 变更后触发重建。
- Agent 经 qdrant-mcp 只读检索。

### 2.4 Web 协作契约（FR-KB-004）

- Outline 经 OIDC 登录；集合级权限区分 dev/boss 视图。
- AI 区（ai-inbox 内容）在 Outline 只读展示，不允许 Web 端编辑。

## 3. HOW

组件部署见 ../how/deployment.md（knowledge profile）；授权背景见 ../why/licensing.md；选型决策见 ../adr/0005-knowledge-stack.md。
