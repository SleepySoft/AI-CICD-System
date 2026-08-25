# ADR-0003 Python 环境用 Miniforge 替代 Anaconda

> 日期：2026-08-21 · 状态：已接受
> 关联：why/licensing.md；需求 FR-IMG-004、NFR-001（一票否决）
> （本篇为文档重构时对原 docs/01 §3.4 决策的追记）

## 背景

2024-03 起 Anaconda 公司要求 200 人以上组织（含 Miniconda 及 defaults 通道）购买商业许可并已实际追费。NFR-001 要求全部组件免费含商用。

## 决策

Python 科学计算/测试栈一律使用 **Miniforge**（仅 conda-forge 通道），禁用 Anaconda 与 defaults 通道。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Anaconda / Miniconda | 授权风险（一票否决） |
| 纯 pip + venv | 可行但失去 conda 生态的科学计算二进制依赖管理优势；保留为镜像内补充手段 |

## 后果

- 正面：完全免费、drop-in 替代、conda-forge 生态完整。
- 负面：个别仅发布在 defaults 通道的包需从 conda-forge 找替代。
- 同步：images/test-python/；why/licensing.md。
