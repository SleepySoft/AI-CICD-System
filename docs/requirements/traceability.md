# 追溯矩阵

> 版本：v1.4 · 日期：2026-09-01 · 状态：生效
> 定位：需求 ID ↔ 设计章节 ↔ 实现位置 ↔ 验证手段。Agent 做 gap 分析的输入；改代码必须同步本表。

## 功能需求（FR）

| 需求 ID | 标题 | 设计章节 | 实现位置 | 验证 |
|---------|------|---------|---------|------|
| FR-ENV-001 | Compose 统一编排 | what/environment.md §服务清单 | chronicler/components/*/compose.yml（组件化部署定义，ADR-0027；无根 compose） | `python -m chronicler test` |
| FR-ENV-002 | 统一域名入口 | what/environment.md §域名契约 | chronicler/components/caddy/Caddyfile | scripts/verify.sh |
| FR-ENV-003 | 统一门户导航 | what/environment.md §服务清单 | chronicler 首页（tools.yaml 注册表驱动，Homepage 已退役） | 人工：登录 Chronicler 首页看入口与状态 |
| FR-ENV-004 | 状态监控 | what/environment.md §服务清单 | chronicler/components/uptime-kuma/ | 人工：Uptime Kuma 面板 |
| FR-ENV-005 | SSO 统一认证 | what/environment.md §SSO 契约 | chronicler/components/keycloak/realm/ | scripts/check-kc.sh |
| FR-CI-001 | push 自动触发流水线 | how/images-toolchain.md | chronicler/components/jenkins/（chronicler-selftest 流水线，GitHub SSH 直拉 + pollSCM 兜底） | 人工：push 后观察 Jenkins 新构建 |
| FR-CI-002 | 一次性容器内构建 | how/images-toolchain.md | chronicler/components/jenkins/（inbound agents） | 人工：构建日志 |
| FR-CI-003 | Allure 报告归档 | how/images-toolchain.md | chronicler/components/jenkins/（allure-jenkins-plugin） | 人工：Jenkins 报告页 |
| FR-CI-004 | Jenkins 配置即代码 | how/images-toolchain.md | chronicler/components/jenkins/casc.yaml + plugins.txt | 重建 Jenkins 容器 |
| FR-IMG-001 | C/C++ 工具链镜像 | how/images-toolchain.md | images/toolchain-cpp/ | scripts/build-images.sh |
| FR-IMG-002 | Android 工具链镜像 | how/images-toolchain.md | images/toolchain-android/ | scripts/build-images.sh |
| FR-IMG-003 | Node 工具链镜像 | how/images-toolchain.md | images/toolchain-node/ | scripts/build-images.sh |
| FR-IMG-004 | Python 测试镜像(Miniforge) | how/images-toolchain.md | images/test-python/ | scripts/build-images.sh |
| FR-IMG-005 | 浏览器自动化镜像 | how/images-toolchain.md | images/browsers/ | scripts/build-images.sh |
| FR-KB-001 | Markdown vault 事实源 | what/knowledge.md §分区规范 | 已废弃（知识改由 shadow 仓/全局资产库承载，ADR-0028/FR-MGR-013/014） | - |
| FR-KB-002 | 来源分区与标注 | what/knowledge.md §frontmatter 契约 | 已废弃（同上，分区约定将迁入 shadow 仓结构） | - |
| FR-KB-003 | 语义检索（Qdrant） | what/knowledge.md §索引契约 | chronicler/components/qdrant/ | 人工：MCP 语义查询 |
| FR-KB-004 | Outline 分级可见 | what/knowledge.md §索引契约 | chronicler/components/outline/ + chronicler/components/keycloak/ | 人工：dev/boss 登录比对 |
| FR-REQ-001 | 需求条目化机器可读 | what/req-mgmt.md | docs/requirements/（本目录）+ Sphinx-Needs(规划) | 本文件自检 |
| FR-REQ-002 | 追踪矩阵自动生成 | what/req-mgmt.md | Sphinx-Needs(规划) | 待实现 |
| FR-REQ-003 | 需求管理界面 | what/req-mgmt.md | chronicler/components/openproject/ | 人工：OpenProject |
| FR-MGR-001 | 工具总览面板 | what/manager.md §前端页面 | chronicler/app/tools.py + chronicler/config/tools.yaml | scripts/verify-chronicler.sh |
| FR-MGR-002 | Agent 终端 | what/manager.md §前端页面 | chronicler/components/terminal-runtime/（可选隔离沙箱，ADR-0021） | 人工：部署 terminal-runtime 后访问 term.localhost/ui |
| FR-MGR-003 | 代码源管理 | what/manager.md §数据模型 | chronicler/（M2 规划） | 待实现（M2） |
| FR-MGR-004 | 任务多方式触发 | what/manager.md §数据模型 | chronicler/（M2-M3 规划） | 待实现（M3） |
| FR-MGR-005 | 一切皆 Run | what/manager.md §数据模型 | chronicler/app/runner.py（输入快照已冻结；重放/重跑待续） | 人工：查看 Run 输入快照 |
| FR-MGR-006 | SSE 实时日志 | what/manager.md §API 概要 | chronicler/（M2 规划） | 待实现（M2） |
| FR-MGR-007 | 内置六类任务 | what/manager.md §任务类型框架 | chronicler/prompts/（六类模板齐备）；执行依赖真实 harness 配置 | 人工：触发各任务类型产生 Run |
| FR-MGR-008 | 报告分级可见 | what/manager.md §权限规格 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-009 | 待审闭环 | what/manager.md §数据模型 | chronicler/（M4 规划） | 待实现（M4） |
| FR-MGR-010 | CI 结果消费 | what/manager.md §数据模型 | chronicler/app/runner.py _ci_context（最小实现：快照记录同期构建） | 人工：Run 快照含 ci_context |
| FR-MGR-011 | Prompt 库版本化 | what/manager.md §数据模型 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-012 | 项目全景仪表盘 | what/manager.md §前端页面 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-013 | 项目影子库 | what/manager.md §数据模型 | chronicler/app/projects.py（ensure_shadow_repo + Gitea 自动建仓）+ runner._commit_shadow（ADR-0028） | 人工：触发任务后查 artifacts 的 commit/pushed 与 Gitea 仓 |
| FR-MGR-014 | 全局资产库 | what/manager.md §数据模型 | chronicler/（M4 规划） | 待实现（M4） |
| FR-MGR-015 | 资源能力注入（skill 化） | what/manager.md §契约要点 | chronicler/app/registry.py（injectable_components）+ chronicler/components/\<name\>/SKILL.md（ADR-0024/0025） | 人工：触发 Run 后查 prompt 快照含 SKILL 路径 |
| FR-MGR-016 | 任务来源适配与降级 | what/manager.md §任务类型框架 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-017 | 分角色鉴权与可插拔鉴权后端 | what/manager.md §权限规格 | chronicler/app/auth.py + routers/users.py + routers/oidc.py（local/oidc 双后端，ADR-0023） | scripts/verify-chronicler.sh（401）；scripts/wire-chronicler.sh（oidc 接线） |
| FR-MGR-018 | 全局组件配置 | what/manager.md §数据模型 | chronicler/config/components.yaml + chronicler/app/registry.py | 人工：改 enabled 后观察 prompt 注入变化 |
| FR-MGR-019 | Agent harness 登记（命令模板） | what/manager.md §数据模型 | chronicler/config/harness.yaml + chronicler/app/runner.py（ADR-0021） | 人工：登记 harness 后触发 Run |
| FR-MGR-020 | 工程实体与配置覆盖 | what/manager.md §数据模型 | chronicler/app/projects.py | 人工：建工程+覆盖项触发 Run |
| FR-MGR-021 | 工程分析策略配置 | what/manager.md §任务类型框架 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-022 | 组件生命周期管理 | what/manager.md §前端页面 | chronicler/app/tools.py + chronicler/components/（ADR-0027） | 人工：自启开关重启验证/日志/详情/一键部署 |
| FR-MGR-023 | 组件自检 | chronicler/app/testing.py | chronicler/app/testing.py + 组件 hooks/test.py | CI：Jenkins chronicler-selftest（push 触发）；本地 `python -m chronicler test [--deploy]` |
| FR-MGR-024 | 人机 Web 终端（Human Terminal） | what/manager.md §前端页面 | chronicler/components/sshwifty/（P0，ADR-0030）+ chronicler/app/terminal（P1 规划） | 人工：浏览器打开终端进入工作区，会话含注入上下文 |
| FR-TASK-001 | 任务前端提交 | what/task-mgmt.md §角色分工 | chronicler/components/openproject/ | 人工：建包后 API 检索 |
| FR-TASK-002 | AI 任务领取 | what/task-mgmt.md §API 契约 | .agents/skills/openproject/（Manager M2 起自动化） | 人工：按 skill 领任务置 in progress |
| FR-TASK-003 | AI 状态回写 | what/task-mgmt.md §状态机 | .agents/skills/openproject/ + OpenProject workflow 配置 | 人工：回写成功且置 closed 被拒 |
| FR-TASK-004 | 任务↔提交关联 | what/task-mgmt.md §关联契约 | 提交信息约定 OP#<id> | 人工：抽查提交↔工作包互查 |
| FR-TASK-005 | 任务手工导出快照 | what/task-mgmt.md §关联契约 | scripts/export-openproject.sh | 人工：运行脚本看 INDEX.md |

## 非功能需求（NFR）

| 需求 ID | 标题 | 落实位置 | 验证 |
|---------|------|---------|------|
| NFR-001 | 全免费含商用 | why/licensing.md；镜像选型；Docker Desktop 可选路径注记（ADR-0020） | 人工：license 清单核查 |
| NFR-002 | 密钥不落明文 | .env.example / .gitignore；chronicler harness env ${VAR} 引用（ADR-0021/0023） | 仓库检索 + 人工核查 |
| NFR-003 | 资源可控/按需启停 | chronicler/components/*/plugin.yaml（autostart 标记）+ 首页工具面板 | docker ps + 首页组件状态 |
| NFR-004 | 一键部署可验证 | scripts/up.sh + README（主入口 serve 校验 .env，ADR-0029） | scripts/verify.sh |
| NFR-005 | 构建可复现 | images/*/Dockerfile 版本锁定 | 重建比对 digest |
| NFR-006 | 三形态同源 | scripts/build-images.sh + 封装脚本；supervisor 独立交付（ADR-0020，待实现） | 人工：封装脚本复用 compose |
| NFR-007 | Agent 成本可控 | chronicler harness 注册表 + chronicler/components/ollama/ | 人工：切换本地模型跑任务 |
| NFR-008 | 数据显式持久化 | 各组件 compose.yml bind mounts（${DATA_ROOT:-./data}，public/private/workspace 三分 ADR-0026）；组件化备份编排 chronicler/app/backup.py + 组件 hooks（ADR-0027），scripts/backup.sh 为薄壳 | `python -m chronicler backup` 产出含 manifest 的备份包 |
| NFR-009 | 系统数据 Git 化 | docs/、shadow 仓（data/public/shadow/，ADR-0028）、chronicler/components/jenkins/casc.yaml（已落实）；scripts/export-openproject.sh（手工导出，ADR-0014） | 抽查数据可定位 Git 事实源 |
