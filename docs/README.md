# 文档索引

> 版本：v1.12 · 日期：2026-09-05 · 状态：生效
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
| 功能需求-Web 初始化 | requirements/functional/initialization.md | requirements | 生效 |
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
| Web 初始化与环境设置规格 | what/initialization.md | what | 生效 |
| Manager 架构与执行机制 | how/manager-architecture.md | how | 生效 |
| Web 初始化模块架构 | how/initialization-architecture.md | how | 生效 |
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
| ADR-0023 supervisor v1 形态（SQLite+本地账密） | adr/0023-supervisor-v1-form.md | adr | 已接受 |
| ADR-0024 组件即 SKILL（渐进披露注入） | adr/0024-component-as-skill.md | adr | 已接受 |
| ADR-0025 SKILL 文件存在即声明（依赖方向澄清） | adr/0025-skill-existence-as-declaration.md | adr | 已接受 |
| ADR-0026 数据目录 public/private 二分 | adr/0026-data-public-private.md | adr | 已接受 |
| ADR-0027 组件目录自包含与钩子契约 | adr/0027-component-directory-hooks.md | adr | 已接受 |
| ADR-0028 持久产物统一入 shadow project | adr/0028-shadow-project-unified-artifacts.md | adr | 已接受 |
| ADR-0029 supervisor 唯一入口与 .env 前置校验 | adr/0029-supervisor-single-entry-env-prereq.md | adr | 已接受 |
| ADR-0030 人机 Web 终端（SSHwifty P0 → Human Terminal） | adr/0030-human-web-terminal-sshwifty.md | adr | 已接受 |
| ADR-0031 Web 终端目标选型（宿主 sshd） | adr/0031-web-terminal-target-host-sshd.md | adr | 已接受 |
| ADR-0032 手动会话注入契约（约定文件+动态 SKILL+chai） | adr/0032-manual-session-skill-injection.md | adr | 已接受 |
| ADR-0033 AI 产物由 Chronicler 统一 Git 发布与 PR 审核 | adr/0033-chronicler-owned-git-publication.md | adr | 已接受 |
| ADR-0034 任务类型与 Prompt 家族通过 registry 解耦 | adr/0034-task-prompt-family-registry.md | adr | 已接受 |
| ADR-0035 以有效输入快照驱动增量提示与自动任务 | adr/0035-effective-input-change-detection.md | adr | 已接受 |
| ADR-0036 构建时固化 sealed Profile 与结构化 Prompt Catalog | adr/0036-sealed-runtime-prompt-catalog.md | adr | 已接受 |
| ADR-0037 初始化收归单一入口（Web 初始化界面，启动脚本回收） | adr/0037-single-entry-web-init.md | adr | 已接受 |
| ADR-0038 受限引导模式与声明式组件初始化 | adr/0038-bootstrap-mode-and-declarative-initialization.md | adr | 已接受 |
| ADR-0039 重新初始化采用恢复式收敛（recover），不提供全新初始化路径 | adr/0039-reinit-recover-over-fresh.md | adr | 已接受 |
| ADR-0040 秘密再导出与重置：按 secret_type 分级 | adr/0040-secret-reexport-and-reset-policy.md | adr | 已接受（第 4 条经 ADR-0041 修订） |
| ADR-0041 秘密的防丢持久化：主密钥 + 加密快照，导出 JSON 不含口令明文 | adr/0041-secret-snapshot-and-master-key.md | adr | 已接受 |
| ADR-0042 文件型秘密（签名证书/keystore）纳入统一秘密管理 | adr/0042-secret-files-signing-assets.md | adr | 已接受 |
| ADR-0043 秘密作用域分权与审计：在线取用为主、离线分发包为辅 | adr/0043-secret-scopes-acl-audit.md | adr | 已接受（离线包形态经 ADR-0044 修订） |
| ADR-0044 多接收者密钥体系：系统秘密仅 admin 可解，工程秘密按接收者集合加密 | adr/0044-recipient-key-hierarchy.md | adr | 已接受 |
| 部署与初始化 | runbooks/deploy.md | runbooks | 生效 |
| 备份与恢复 | runbooks/backup-restore.md | runbooks | 生效 |
| 接入新 Agent | runbooks/agent-onboarding.md | runbooks | 生效 |
| 手动启动与调试 Chronicler | runbooks/dev-debug.md | runbooks | 生效 |
| Keycloak 用户与权限管理 | runbooks/keycloak-users.md | runbooks | 生效 |
| Web 终端（SSHwifty）接入与使用 | runbooks/web-terminal.md | runbooks | 生效 |
| 构建与安装 sealed Chronicler | runbooks/build-sealed-chronicler.md | runbooks | 生效 |
| Clash Verge 代理排查 | runbooks/proxy-clash.md | runbooks | 生效 |
| 秘密库操作手册 | runbooks/vault.md | runbooks | 生效 |
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
| Web 初始化与环境设置 | why/principles.md | what/initialization.md | how/initialization-architecture.md | requirements/functional/initialization.md |
