---
name: qdrant
description: 语义检索——在过往报告/经验/文档中按语义搜索。当任务需要"以史为鉴"（查以前是否分析过、有无相关经验）时使用；组件未启用时跳过检索，直接分析。
---

# Qdrant（语义检索）

## 能干什么

- 语义搜索历史产出：`POST {base}/collections/{collection}/points/query`（或 scroll 全量翻页）
- 用途：让新一轮分析站在过往积累之上（Chronicler 的回注通道，ADR-0022 飞轮第④环）

## 不能干什么

- 不是结构化查询数据库（精确字段过滤用 Postgres/API）
- 不存储原文本体（本体在 git/文件，这里只有索引与摘要）

## 怎么访问

- base URL：`http://vectors.localhost`（宿主）或 `http://qdrant:6333`（容器内）
- 无需认证（内网组件）；组件未部署时视为不可用，直接跳过检索

## 何时选我而非别人

- 需要"找类似/找历史经验"时用我；需要精确提交记录时用 git/Gitea。
