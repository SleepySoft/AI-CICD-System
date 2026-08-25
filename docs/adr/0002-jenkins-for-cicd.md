# ADR-0002 CI/CD 选 Jenkins（Controller + Docker inbound agents）

> 日期：2026-08-21 · 状态：已接受
> 关联：how/images-toolchain.md；需求 FR-CI-001 ~ FR-CI-004
> （本篇为文档重构时对原 docs/01 §3.2 决策的追记）

## 背景

需求指定 Jenkins 做 CI。需要流水线编译/测试/打包，构建在可复现容器内执行，配置可重建（FR-CI-004）。

## 决策

Jenkins Controller + Docker inbound agents 架构；全部配置用 JCasC + plugins.txt 固化进镜像。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Gitea Actions | 更轻，但生态和凭据管理不如 Jenkins；且需求已指定 Jenkins |
| GitLab CI | 依附 GitLab，已被 ADR-0001 排除 |

## 后果

- 正面：插件生态成熟；定时 Agent 任务也可做成 Jenkins 流水线，集中可见。
- 负面：Jenkins 运维偏重；配置复杂度高（用 JCasC 对冲）。
- 同步：jenkins/（Dockerfile、casc.yaml、plugins.txt）。
