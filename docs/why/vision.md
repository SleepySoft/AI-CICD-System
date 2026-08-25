# 项目愿景与边界

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：回答"为什么做、做成什么样、不做什么"。规格见 ../what/，机制见 ../how/
> 关联需求：BR-001 ~ BR-009

## 1. WHY — 动机

交付一套可一键部署的集成研发环境（Docker 镜像 + 部署脚本 + 管理界面），让 AI Agent 在其中自动完成代码分析、文档生成、需求比对与知识沉淀（BR-001 ~ BR-009）。

## 2. WHAT — 目标摘要

环境分四层（Context 级视图）：

```
访问层      Homepage 门户 / Keycloak SSO / Uptime Kuma 状态页
Agent 层    Agent CLI + MCP 工具链 + 调度 + 文档站产出
平台服务层  Gitea / Jenkins / OpenProject / Qdrant / Outline / Ollama
构建运行时  toolchain-cpp · toolchain-android · toolchain-node · test-python · browsers
基础设施    Docker Compose（唯一事实源）；WSL/VM 镜像只是其封装
```

## 3. HOW

实现机制见 ../how/deployment.md（交付形态与部署）、../how/manager-architecture.md（Manager）。

## 4. Non-Goals（明确不做）

- **Manager 不替代 CI/CD**：构建、测试、发布永远走 Jenkins；Manager 只做分析与洞察（消费 CI 结果）。
- **不引入 K8s**：单容器/compose 粒度足够，执行容器经 docker.sock 拉起。
- **Obsidian 只是本地编辑器**：系统侧知识库不依赖它，vault 才是事实源。
- **不追求大而全的需求管理 GUI 自研**：组合 OpenProject + 需求即代码（见 ADR-0006）。
- **不做 Agent 训练/微调**：只做 Agent 的编排、接入与产出管理。

## 5. 演进方向

环境侧里程碑：M1 骨架（compose 核心栈 + 最小部署）→ M2 工具链镜像与示例流水线 → M3 知识与需求层 → M4 Agent 层 → M5 交付封装。Manager 侧里程碑见 ../what/manager.md §里程碑。
