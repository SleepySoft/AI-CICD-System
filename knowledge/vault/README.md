# AISystem 知识库 Vault（单一事实源）

纯 Markdown 知识库，建议初始化为 Git 仓库并推送到 Gitea（如 `knowledge/vault`）。
可用 Obsidian / Logseq 直接打开本目录编辑。

## 目录约定（解决"人工补充与 AI 分析混淆"）

| 目录 | 写入者 | 说明 |
|------|--------|------|
| `human/` | 人 | 用户手工补充的信息，AI 只读不写 |
| `ai-inbox/` | AI | Agent 产出的草稿，**待人工确认** |
| `know-how/` | 人确认后 | 从 ai-inbox 转正的知识与经验，按主题分子目录 |

## Frontmatter 规范

每篇笔记头部必须带元数据：

```markdown
---
origin: human | ai        # 来源
reviewed: true | false    # AI 产出是否经人工确认
visibility: dev | boss    # 可见范围（boss 私有 know-how 用 boss）
tags: []
created: YYYY-MM-DD
---
```

## 索引

内容变更后由 Agent/脚本重建 Qdrant 向量索引（embedding 走本地 Ollama bge-m3）。
