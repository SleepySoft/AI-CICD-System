# ADR-0001 代码托管平台选 Gitea

> 日期：2026-08-21 · 状态：已接受
> 关联：what/environment.md；需求 FR-ENV-001、BR-005（包注册表）
> （本篇为文档重构时对原 docs/01 §3.1 决策的追记，背景为该时点已知信息）

## 背景

需要私有代码托管 + PR/Issue/Webhook + 完整 REST API（供 Agent 读取 commit/diff），且 CI 已指定 Jenkins（ADR-0002）。资源受限（NFR-003）。

## 决策

选 **Gitea** 作为代码托管平台。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| GitLab CE | 资源占用大（≥4GB 内存起步）、升级重；内置 CI 与 Jenkins 重叠，白付资源成本 |
| Gogs | 功能与生态弱于 Gitea |
| 维持现状（无私有托管） | 不满足私有托管与 Webhook 需求 |

## 后果

- 正面：~150MB 内存；API 完整；自带包注册表承接 BR-005（通用功能发布到 Gitea Packages）。
- 负面：无内置 CI，需依赖 Jenkins（已有）。
- 同步：what/environment.md、docker-compose.yml。
