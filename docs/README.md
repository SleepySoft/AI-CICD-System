# 文档索引

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：docs/ 全部文档的目录与状态总表；写作规范见 `.agents/skills/docs-management/`

## 文档总表

| 文档 | 路径 | 层/域 | 状态 |
|------|------|-------|------|
| 文档索引（本文件） | README.md | 入口 | 生效 |
| 需求库说明与模块注册 | requirements/README.md | requirements | 生效 |
| 业务需求 | requirements/business.md | requirements | 生效 |
| 干系人需求 | requirements/stakeholder.md | requirements | 生效 |
| 非功能需求 | requirements/non-functional.md | requirements | 生效 |
| 功能需求-环境编排 | requirements/functional/env.md | requirements | 生效 |
| 功能需求-CI 流水线 | requirements/functional/ci.md | requirements | 生效 |
| 功能需求-工具链镜像 | requirements/functional/images.md | requirements | 生效 |
| 功能需求-知识库 | requirements/functional/kb.md | requirements | 生效 |
| 功能需求-需求管理 | requirements/functional/req.md | requirements | 生效 |
| 功能需求-任务管理 | requirements/functional/task.md | requirements | 生效 |
| 功能需求-Manager | requirements/functional/manager.md | requirements | 生效 |
| 追溯矩阵 | requirements/traceability.md | requirements | 生效 |
| 项目愿景与边界 | why/vision.md | why | 生效 |
| 设计原则 | why/principles.md | why | 生效 |
| 授权与合规背景 | why/licensing.md | why | 生效 |
| 风险与对策 | why/risks.md | why | 生效 |
| 环境规格 | what/environment.md | what | 生效 |
| Manager 规格 | what/manager.md | what | 生效 |
| 知识库规格 | what/knowledge.md | what | 生效 |
| 需求管理工具链规格 | what/req-mgmt.md | what | 生效 |
| 任务管理规格 | what/task-mgmt.md | what | 生效 |
| Manager 架构与执行机制 | how/manager-architecture.md | how | 生效 |
| 部署与交付机制 | how/deployment.md | how | 生效 |
| 工具链镜像机制 | how/images-toolchain.md | how | 生效 |
| SSO 接线机制 | how/sso-wiring.md | how | 生效 |
| ADR-0001 Gitea | adr/0001-gitea-as-git-platform.md | adr | 已接受 |
| ADR-0002 Jenkins | adr/0002-jenkins-for-cicd.md | adr | 已接受 |
| ADR-0003 Miniforge | adr/0003-miniforge-replaces-anaconda.md | adr | 已接受 |
| ADR-0004 Keycloak SSO | adr/0004-keycloak-sso-rbac.md | adr | 已接受 |
| ADR-0005 知识库栈 | adr/0005-knowledge-stack.md | adr | 已接受 |
| ADR-0006 需求管理双层 | adr/0006-openproject-sphinx-needs.md | adr | 已接受 |
| ADR-0007 Manager 独立于 Jenkins | adr/0007-manager-separate-from-jenkins.md | adr | 已接受 |
| ADR-0008 APScheduler | adr/0008-apscheduler-over-celery.md | adr | 已接受 |
| ADR-0009 报告落文件卷 | adr/0009-reports-on-file-volume.md | adr | 已接受 |
| ADR-0010 Vue3 前端 | adr/0010-vue3-frontend.md | adr | 已接受 |
| ADR-0011 任务管理（OpenProject + AI 回写） | adr/0011-openproject-task-management.md | adr | 已接受 |
| ADR-0012 数据显式挂载宿主目录 | adr/0012-data-on-host-bind-mounts.md | adr | 已接受 |
| ADR-0013 系统数据 Git 化 | adr/0013-git-managed-system-data.md | adr | 已接受 |
| ADR-0014 OpenProject 手工导出 | adr/0014-openproject-manual-export.md | adr | 已接受 |
| ADR-0015 备份策略（一键双模式） | adr/0015-backup-strategy.md | adr | 已接受 |
| ADR-0016 ATR 改 submodule | adr/0016-atr-as-submodule.md | adr | 已接受 |
| ADR-0017 Agent 后装与登录持久化 | adr/0017-agent-lifecycle.md | adr | 部分被 ADR-0021 推翻 |
| ADR-0018 Agent 注册表过渡（YAML） | adr/0018-agent-registry-yaml.md | adr | 已接受 |
| ADR-0019 Manager 运行拓扑（容器化+宿主引导器） | adr/0019-manager-runtime-topology.md | adr | 已被 ADR-0020 推翻 |
| ADR-0020 Manager 出容器为宿主侧 supervisor | adr/0020-manager-out-of-docker-supervisor.md | adr | 已接受 |
| ADR-0021 Agent 用户自装 harness 模型 | adr/0021-agent-user-installed-harness.md | adr | 已接受 |
| ADR-0022 产品定位与命名 Chronicler | adr/0022-product-positioning-chronicler.md | adr | 已接受 |
| 部署与初始化 | runbooks/deploy.md | runbooks | 生效 |
| 备份与恢复 | runbooks/backup-restore.md | runbooks | 生效 |
| 接入新 Agent | runbooks/agent-onboarding.md | runbooks | 生效 |
| 旧-需求分析与选型 | 01-需求分析与选型.md | 历史 | 过时（已拆分至本结构） |
| 旧-Manager 设计 | 02-管理服务设计.md | 历史 | 过时（已拆分至本结构） |

## 阅读路径

- 想了解为什么做：`why/vision.md` → `requirements/business.md` → `adr/`
- 想集成/调用：`what/`（环境契约、Manager API、知识库契约）
- 想改实现：`how/` 对应模块 → `requirements/traceability.md` 反查影响的需求
- 想部署/运维：`runbooks/`
- 想确认某条需求落地没有：`requirements/traceability.md`

## 模块注册表

| 模块 | why | what | how | requirements |
|------|-----|------|-----|--------------|
| 环境编排 | why/vision.md | what/environment.md | how/deployment.md | requirements/functional/env.md |
| CI 与镜像 | why/principles.md | what/environment.md | how/images-toolchain.md | requirements/functional/ci.md, images.md |
| 知识库 | why/principles.md | what/knowledge.md | how/deployment.md | requirements/functional/kb.md |
| 需求管理 | why/vision.md | what/req-mgmt.md | how/deployment.md | requirements/functional/req.md |
| 任务管理 | why/vision.md | what/task-mgmt.md | .agents/skills/openproject/ | requirements/functional/task.md |
| Manager | why/vision.md | what/manager.md | how/manager-architecture.md | requirements/functional/manager.md |
