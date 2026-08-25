# 授权与合规背景

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：NFR-001（全免费含商用）的事实依据与已核实的授权结论
> 关联需求：NFR-001

## 1. WHY — 为什么单列

授权风险是本项目选型的**一票否决项**（NFR-001）。以下结论已逐一核实，是选型决策的前置输入；相关决策见 ../adr/0003-miniforge-replaces-anaconda.md 与 ../adr/0005-knowledge-stack.md。

## 2. WHAT — 已核实的授权事实

- **Anaconda（含 Miniconda + defaults 通道）**：2024-03 起，Anaconda 公司要求 **200 人以上的组织**购买商业许可，并已实际发起诉讼/追费。Miniconda 不再是安全选项。→ 替代：**Miniforge**（社区维护、仅 conda-forge 通道，完全免费，drop-in 替代）。
- **Obsidian**：自 2025-02-20 起商用免费。但系统侧不依赖它（见 vision.md Non-Goals），它仅是用户可选的本地编辑器。
- **关键组件许可**：Gitea（MIT）、Jenkins（MIT）、Keycloak（Apache-2.0）、Qdrant（Apache-2.0）、OpenProject CE（GPLv3）、Caddy（Apache-2.0）、Miniforge（BSD-3-Clause）、Playwright（Apache-2.0）。

## 3. HOW — 持续合规机制

- 新增组件时必须核查许可并更新本文件清单。
- 选型倾向 OSI 许可（MIT/Apache/GPL）；对"免费但非 OSI"的组件（如 Obsidian）只作为用户侧可选项，不进入系统依赖。
- 规划：安装器内置 license 清单检查（见 risks.md 对策）。
