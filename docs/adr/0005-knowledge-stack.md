# ADR-0005 知识库栈：Markdown vault + Qdrant + Outline

> 日期：2026-08-21 · 状态：已接受
> 关联：what/knowledge.md；需求 FR-KB-001 ~ FR-KB-004、BR-007
> （本篇为文档重构时对原 docs/01 §3.8 决策的追记）

## 背景

知识库需要：语义检索（RAG 供 Agent）+ 人工笔记双链 + Web 协作 + 人工/AI 来源隔离（BR-007）+ dev/boss 分级可见（BR-008）。

## 决策

三层组合：**Markdown vault（存 Gitea，唯一事实源）+ Qdrant（向量索引，embedding 用本地 Ollama bge-m3）+ Outline（Web 协作，OIDC + 集合权限）**；来源隔离用目录分区 + frontmatter（`origin`/`reviewed`）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 仅用 Outline 存知识 | 闭源格式锁定风险、Agent 不可直接读、无法 git 版本化 |
| 仅用 Obsidian 生态 | Obsidian 只是本地编辑器，无服务端协作与权限 |
| Elasticsearch/OpenSearch 做检索 | 语义检索需额外向量插件，运维重于 Qdrant |
| Logseq 替代 Obsidian | 不冲突——作为用户侧开源备选保留，不影响系统侧设计 |

## 后果

- 正面：vault 版本化、人机共读；索引层可全量重建；AI 产出隔离可控。
- 负面：三个组件需保持同步（索引进度、权限映射）。
- 同步：knowledge/vault/、docker-compose.yml（knowledge profile）、what/knowledge.md。
