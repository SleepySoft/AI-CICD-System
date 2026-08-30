# 项目愿景与边界

> 版本：v1.1 · 日期：2026-08-27 · 状态：生效
> 定位：回答"为什么做、做成什么样、不做什么"。规格见 ../what/，机制见 ../how/
> 关联需求：BR-001 ~ BR-009；定位决策 ADR-0022（Chronicler 为本体）

## 1. WHY — 动机

研发团队的工作产物（代码、文档、决策）散落在各处，AI Agent 能分析却缺乏统一的编排与监督：谁让它跑、跑的什么、产出去了哪、经验如何复用。**Chronicler（史官）**回答这个问题：它默默调查与蒸馏被管理的工作，检查进度，发现与设计的偏离，提取经验——后续开发站在这些积累之上，更有针对性地实现（ADR-0022）。

## 2. WHAT — 目标摘要

> 系统边界（2026-08-29 定调）：**Chronicler 只管理资源和组件、负责注入 prompt 和组织结果；
> task 与 prompt 自由实现任意功能**。引擎不内置任何具体分析逻辑——能力全来自
> prompt 模板 + 组件 SKILL + harness 三者的自由组合。

产品形态分两层（ADR-0020/0021/0022）：

```
产品本体    Chronicler supervisor（宿主侧进程）：工程管理 / harness 编排 /
            任务执行与 Run 档案 / 组件生命周期 / 报告与资产沉淀
可选底座    Docker Compose 栈（Gitea / Jenkins / Keycloak / OpenProject /
            Qdrant / Outline …）——为没有现成基础设施的团队一键配齐，各组件均可替换
执行方式    用户自装的 agent harness（kimi/claude/aider…），命令模板登记，
            宿主真实路径执行；terminal-runtime 为可选隔离沙箱
```

关键边界：底座可整体缺失（无底座单机 = Chronicler + git 即可运行），也可逐组件替换（git 远端任意、任务源可降级，FR-MGR-016）。

## 3. HOW

实现机制见 ../how/manager-architecture.md（supervisor 架构与执行管线）、../how/deployment.md（两段式交付）。

## 4. Non-Goals（明确不做）

- **Chronicler 不替代 CI/CD**：构建、测试、发布永远走 Jenkins 等 CI；Chronicler 只做分析与洞察（消费 CI 结果）。
- **不引入 K8s**：单容器/compose 粒度足够。
- **不接管 agent harness 的安装与登录**：用户自装自管（ADR-0021），supervisor 只登记命令模板。
- **不做 Agent 训练/微调**：只做编排、接入与产出管理。
- **不追求大而全的需求管理 GUI 自研**：组合 OpenProject + 需求即代码（见 ADR-0006），且可整体缺席。

## 5. 演进方向

M1 环境骨架（compose 栈）✅ → M2 supervisor v1（宿主化、鉴权、工程+harness+Run 闭环、组件生命周期）✅ → M3 内置任务全量 + 待审闭环 → M4 shadow/全局资产库 → M5 CI 综合报告 → M6 Nuitka 保密打包。详见 ../what/manager.md §里程碑。
