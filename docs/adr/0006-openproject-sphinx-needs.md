# ADR-0006 需求管理：OpenProject（GUI）+ Sphinx-Needs（需求即代码）双层方案

> 日期：2026-08-21 · 状态：已接受
> 关联：what/req-mgmt.md；需求 FR-REQ-001 ~ FR-REQ-003、BR-003
> （本篇为文档重构时对原 docs/01 §3.7 决策的追记）

## 背景

BR-003 要求 Agent 比对代码与需求，前提是需求机器可读（带 ID 条目化）。Jama 没有开源等价物，单一工具无法同时满足 GUI 管理与机器可读。

## 决策

双层方案：**OpenProject CE** 做管理界面（条目/状态/看板/API），**Sphinx-Needs** 做机器可读层（需求带 ID 进 Git，导出 JSON 喂给 Agent，自动生成追踪矩阵），两层经 API 同步。本仓库自身的需求采用其最小实现：`docs/requirements/`（markdown + ID）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 自研需求管理 GUI | Non-Goal（why/vision.md），投入产出比极低 |
| 仅用 OpenProject | 需求不可机器读，BR-003 无法满足 |
| 仅用 Gitea Issue + markdown 模板 | 保留为降级方案（部署向导可选），追踪矩阵能力弱 |
| doorstop 替代 Sphinx-Needs | 功能相近；Sphinx-Needs 生态与文档生成集成更好 |

## 后果

- 正面：人与 Agent 各取所需；追踪矩阵可自动生成。
- 负面：两层同步需维护；OpenProject 有一定资源占用（挂 requirements profile 按需启用）。
- 同步：what/req-mgmt.md、docs/requirements/。
