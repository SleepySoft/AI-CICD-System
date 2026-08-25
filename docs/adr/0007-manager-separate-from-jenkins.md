# ADR-0007 分析任务不放 Jenkins，由 Manager 独立承载

> 日期：2026-08-21 · 状态：已接受
> 关联：how/manager-architecture.md；需求 FR-MGR-003 ~ FR-MGR-011
> （本篇为文档重构时对原 docs/02 §13.1 决策的追记）

## 背景

Agent 分析任务（文档生成、gap 分析、日报等）需要丰富的输入编排、人审交互、报告生命周期管理。已决定用 Jenkins 做 CI（ADR-0002），问题是分析任务是否也放 Jenkins。

## 决策

分析任务由独立的 **Manager** 服务承载；Jenkins 只做构建与测试，其结果作为 Manager 的输入被消费。两者互补不冲突。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 全部做成 Jenkins 定时流水线 | Jenkins 适合确定性构建；人审交互、报告生命周期、输入编排放 Jenkins 内聚性差 |
| 独立 worker 集群（K8s Job） | 违反"不引入 K8s"的 Non-Goal |

## 后果

- 正面：分析任务闭环内聚（任务即配置、一切皆 Run、人审闭环）；CI/CD 边界清晰。
- 负面：多一个服务维护；需消费 Jenkins REST 做结果关联。
- 同步：what/manager.md、how/manager-architecture.md。
