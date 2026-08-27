# ADR-0022 产品定位澄清与命名：Chronicler（supervisor 为本体，compose 栈为可选底座）

> 日期：2026-08-27 · 状态：已接受
> 关联：why/vision.md（定位待回写）；需求 NFR-006、NFR-009、BR-008；ADR-0014、ADR-0020、ADR-0021

## 背景

ADR-0020/0021 之后，Manager 成为 docker 宿主侧的 supervisor，直接驱动用户自装 harness 分析代码/文档资产。复核其对外依赖发现硬依赖极少：

- 代码源契约本就支持**任意 git 远端**（`repo_source.url` 含 GitHub/Gitea），Gitea 不是硬依赖；
- OpenProject 已经 ADR-0014 解耦为可选（手工导出快照）；
- 分析产出主要是 **Markdown、提交到指定 git 仓库**（NFR-009：Git 是系统数据事实源，DB 仅为可重建运行时层）。

即：compose 栈（Gitea / Jenkins / Keycloak / OpenProject …）是可替换、可选装的基础设施，而 supervisor 是跨环境复用的产品本体。同时需要为产品定名，决策时刻给定的命名要求：名字须暗含如下象征——**默默调查与蒸馏被管理的工作，检查进度，发现与设计的偏离，提取经验；今后基于它再做开发可复用此前积累的经验与组件，从而更有针对性地实现**。

## 决策

1. **定位**：supervisor 是产品本体；compose 栈降级为"默认自带的可选底座"——为没有现成基础设施的团队一键配齐 git/CI/SSO/任务管理，各组件均为可替换适配器。
2. **命名**：产品名 **Chronicler**（史官）——默默记录被管理的工作，以史为鉴，供后续开发借鉴复用。文档与代码中 "supervisor" 保留为角色词，Chronicler 为产品名。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持"环境为主体、Manager 管理环境"的定位 | 与实际依赖关系不符：git 远端/任务管理/SSO 均可替换，产出落任意 git |
| 命名 Surveyor（测量师） | 偏离检测与复用贴切，但"蒸馏/记录"意味弱 |
| 命名 Lodestar（指引星） | "暗中指引"传神，但缺主动勘察的动作感 |
| 命名 Gleaner（拾穗者） | 经验复用传神，但盖不住"检查进度/发现偏离"；且近 Glean（知名产品） |

## 后果

- 正面：产品边界清晰——Chronicler 可独立于 compose 栈交付与演进，栈只是它的一种底座；命名统一后续代码/文档/二进制的措辞。
- 负面：仓库名 `AI-CICD-System` 与目录名 `manager/` 与新定位不符，更名牵涉 remote/路径/引用，随 supervisor 实现时再定。
- 待办：`why/vision.md` 定位回写（从"一体化 AI 研发环境"到"Chronicler + 可选底座"）；`manager/` → `chronicler/` 目录与产物命名随实现迁移；单机瘦身选项（Postgres→SQLite、Keycloak→本地账密）记录在案，**本次未决策**。
- 同步：docs/README.md 索引登记本篇；vision.md 回写与其余文档债统一登记在根 AGENTS.md"文档同步债"。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
