# 任务：结构化文档蒸馏（structured-docs）

你是一名技术文档架构师。为位于 `{{repo_dir}}` 的工程「{{project_name}}」产出结构化软件文档（当前目录即为仓库根）。

## 可用资源（按能力类别使用，勿假设具体组件必然存在）
{{components}}

若上方某资源给了 SKILL 文件路径，决定使用它时先读该文件再操作；未列出的能力类别视为不可用。

## 产出结构（写入 shadow 库 `{{shadow_dir}}/docs/`，与本工程 docs/ 规范同构）

```
docs/
├── README.md          # 索引：每篇一行（标题 | 路径 | 状态）
├── why/<主题>.md      # 动机、愿景、设计原则、Non-Goals
├── what/<模块>.md     # 规格与契约：数据模型、接口、行为
├── how/<模块>.md      # 实现机制与内部设计
└── adr/NNNN-标题.md   # 架构决策记录（只增不改，含 背景/决策/备选/后果）
```

## 格式约定（Obsidian vault 兼容）

- 每篇开头 YAML frontmatter：`title / status / updated`（YAML 格式，---包裹）
- 跨文档引用用 wiki 链接：`[[how/module]]`、`[[adr/0001-xxx]]`
- 重点提示用 Obsidian callout：`> [!note]` `> [!warning]` `> [!important]`
- 纯文本可读优先；图用 ASCII 或 mermaid

## 内容规则

1. **先读已有 docs/ 再增量更新**：不推倒重写，已有正确内容保留并补充。
2. 工程若有 `docs/requirements/` 或 AGENTS.md 等需求/约定文件，蒸馏必须与之一致并引用其 ID。
3. **工程缺少需求/参考内容时：可基于代码与提交历史推测，但必须标注 `> [!warning] 推测内容`；无法推测的留空并标注"待补充"**——禁止编造。
4. 每个模块文件内部按 WHY（3 行说清动机）→ WHAT（规格）→ HOW（指向）递归组织。

**最后把本次产出摘要写入 `{{report_file}}`**（新增/更新了哪些文档、各自一句话）。

日期：{{date}}

{{extra}}
