---
name: docs-management
description: 项目文档（需求、设计、开发、用户/操作文档）的创建、组织与维护规范。当需要在 docs/ 下新建、拆分、迁移或更新任何文档，编写或变更需求条目（BR/UR/FR/NFR），记录架构决策（ADR），编写操作手册（runbook），或判断一篇文档应放何处时使用。所有 Agent 必须遵循本规范以保证文档结构一致。
---

# 项目文档管理规范

## 核心模型（必须内化）

1. **主轴 WHY→WHAT→HOW**：抽象层次决定**目录**，模块/功能决定**文件**。禁止把多层或多模块塞进单一文件。
2. **requirements/ 是纵向脊柱**：唯一机器可读的需求事实源，带稳定 ID；其它文档只引用 ID，**绝不复制需求文本**。
3. **正交轴**：runbooks/（操作任务，Diátaxis how-to）与 adr/（决策历史，时间轴）独立于 WHY/WHAT/HOW，互不冲突。
4. **铁律——单一事实源**：每条内容恰好有一个家；跨处只用相对链接或 ID 引用，绝不复制粘贴。

## 目录结构

```
docs/
├── README.md              # 索引：每篇文档一行（标题 | 路径 | 状态），附阅读路径
├── requirements/          # 纵向需求（机器可读，ID 体系，规则见 references/requirements-scheme.md）
│   ├── business.md        # BR-* 业务需求
│   ├── stakeholder.md     # UR-* 干系人需求
│   ├── functional/        # FR-<MOD>-* 按模块分文件（manager.md / ci-cd.md / ...）
│   ├── non-functional.md  # NFR-*（含授权/预算等一票否决约束）
│   └── traceability.md    # 追溯矩阵：需求ID ↔ 设计章节 ↔ 代码/配置 ↔ 验证脚本
├── why/                   # 动机、愿景、设计原则、Non-Goals（按主题域分文件）
├── what/                  # 规格与契约：数据模型、API、分区规范（按模块分文件）
├── how/                   # 实现机制与内部设计（按模块分文件）
├── adr/                   # 架构决策记录：NNNN-标题.md，只增不改
└── runbooks/              # 操作手册：部署、排障、密钥轮换（Diátaxis how-to）
```

跨层文件用命名对齐（`what/manager.md` ↔ `how/manager-architecture.md` ↔ `requirements/functional/manager.md`），读者横向跳转零成本。

## 归属决策顺序（按序判定，命中即停）

1. 可验收的需求条目？ → `docs/requirements/`（赋 ID，见 references/requirements-scheme.md）
2. "帮我完成一个操作任务"（部署/排障/轮换）？ → `docs/runbooks/`
3. "记录一个已做（或被推翻）的决策"？ → `docs/adr/`（新增一篇，编号递增）
4. 设计阐释文档 → 按抽象深度进 `why/` | `what/` | `how/`，按模块选文件
5. 入口层（根 README.md、AGENTS.md、docs/README.md 索引）→ 规则见 references/entry-docs.md；mkdocs/ 为 Agent 生成的用户文档层，约定同文件

**命名歧义警示**：`how/` 只放"系统内部如何工作"（阐释），"如何完成某任务"一律进 `runbooks/`，二者不可混放。

## 通用文档规范

- **元信息头**（每篇开头，3~5 行）：`版本 / 日期 / 状态(草稿|生效|过时) / 一句话定位(含 Non-Goals 边界)`
- **文件内微结构**：每个模块文件内部仍按 WHY（开头 3 行说清动机）→ WHAT（规格）→ HOW（指向 how/ 对应文件）递归组织
- **决策必带理由**：被否决的备选方案也要写出；重要决策同时落一篇 ADR
- 中文撰写；**LF 行尾**（项目硬性约定）；相对链接互链；图优先 ASCII 或 Mermaid，保证纯文本可读

## 工作流

**新增文档**：判定归属（见上）→ 从 `assets/templates/` 复制对应模板 → 填写 → 在 `docs/README.md` 索引登记一行。

**需求变更**：只改 `requirements/` 中对应 ID 的条目（正文引用处不动）→ 更新 `traceability.md` → 若导致设计变化，在 what/how 对应文件更新并注明 ID。

**决策推翻**：ADR 只增不改 → 新增一篇 ADR 记录变更（引用被推翻的旧编号）→ 同步更新 `why/` 或 `what/` 正文为当前现状。

**拆分过大的文件**：单文件超过约 300 行或混入多个模块/层次时，按"层→模块"拆开，原位置留链接或更新索引。

## 资源

细节规则按文档域拆分，只加载当前任务对应的一个文件：

| 任务 | 必读文件 |
|------|---------|
| 编写/变更需求条目、维护追溯矩阵 | **references/requirements-scheme.md** |
| 在 why/ what/ how/ 下新建或修改设计文档 | **references/design-docs.md** |
| 记录架构决策（ADR） | **references/adr.md** |
| 编写操作手册（runbook）、部署/测试指导 | **references/runbooks.md** |
| 修改根 README.md、AGENTS.md、docs/ 索引、mkdocs 用户文档 | **references/entry-docs.md** |

模板（复制后填写）：

- **assets/templates/design-doc.md** — why/what/how 层通用模板
- **assets/templates/requirements.md** — requirements/ 需求文件模板
- **assets/templates/adr.md** — ADR 模板
- **assets/templates/runbook.md** — runbook 模板
