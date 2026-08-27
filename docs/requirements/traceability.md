# 追溯矩阵

> 版本：v1.3 · 日期：2026-08-27 · 状态：生效
> 定位：需求 ID ↔ 设计章节 ↔ 实现位置 ↔ 验证手段。Agent 做 gap 分析的输入；改代码必须同步本表。

## 功能需求（FR）

| 需求 ID | 标题 | 设计章节 | 实现位置 | 验证 |
|---------|------|---------|---------|------|
| FR-ENV-001 | Compose 统一编排 | what/environment.md §服务清单 | docker-compose.yml | `docker compose config -q` |
| FR-ENV-002 | 统一域名入口 | what/environment.md §域名契约 | caddy/Caddyfile | scripts/verify.sh |
| FR-ENV-003 | 统一门户导航 | what/environment.md §服务清单 | chronicler 首页（tools.yaml 注册表驱动，Homepage 已退役） | 人工：登录 Chronicler 首页看入口与状态 |
| FR-ENV-004 | 状态监控 | what/environment.md §服务清单 | docker-compose.yml(monitor profile) | 人工：Uptime Kuma 面板 |
| FR-ENV-005 | SSO 统一认证 | what/environment.md §SSO 契约 | keycloak/realm/ | scripts/check-kc.sh |
| FR-CI-001 | push 自动触发流水线 | how/images-toolchain.md | jenkins/ + Gitea webhook | 人工：push 触发一次构建 |
| FR-CI-002 | 一次性容器内构建 | how/images-toolchain.md | jenkins/（inbound agents） | 人工：构建日志 |
| FR-CI-003 | Allure 报告归档 | how/images-toolchain.md | jenkins/（allure-jenkins-plugin） | 人工：Jenkins 报告页 |
| FR-CI-004 | Jenkins 配置即代码 | how/images-toolchain.md | jenkins/casc.yaml + plugins.txt | 重建 Jenkins 容器 |
| FR-IMG-001 | C/C++ 工具链镜像 | how/images-toolchain.md | images/toolchain-cpp/ | scripts/build-images.sh |
| FR-IMG-002 | Android 工具链镜像 | how/images-toolchain.md | images/toolchain-android/ | scripts/build-images.sh |
| FR-IMG-003 | Node 工具链镜像 | how/images-toolchain.md | images/toolchain-node/ | scripts/build-images.sh |
| FR-IMG-004 | Python 测试镜像(Miniforge) | how/images-toolchain.md | images/test-python/ | scripts/build-images.sh |
| FR-IMG-005 | 浏览器自动化镜像 | how/images-toolchain.md | images/browsers/ | scripts/build-images.sh |
| FR-KB-001 | Markdown vault 事实源 | what/knowledge.md §分区规范 | knowledge/vault/ | 人工：vault git 仓库 |
| FR-KB-002 | 来源分区与标注 | what/knowledge.md §frontmatter 契约 | knowledge/vault/ | 人工：frontmatter 抽查 |
| FR-KB-003 | 语义检索（Qdrant） | what/knowledge.md §索引契约 | docker-compose.yml(knowledge profile) | 人工：MCP 语义查询 |
| FR-KB-004 | Outline 分级可见 | what/knowledge.md §索引契约 | docker-compose.yml + Keycloak | 人工：dev/boss 登录比对 |
| FR-REQ-001 | 需求条目化机器可读 | what/req-mgmt.md | docs/requirements/（本目录）+ Sphinx-Needs(规划) | 本文件自检 |
| FR-REQ-002 | 追踪矩阵自动生成 | what/req-mgmt.md | Sphinx-Needs(规划) | 待实现 |
| FR-REQ-003 | 需求管理界面 | what/req-mgmt.md | docker-compose.yml(requirements profile) | 人工：OpenProject |
| FR-MGR-001 | 工具总览面板 | what/manager.md §前端页面 | chronicler/app/tools.py + chronicler/config/tools.yaml | scripts/verify-chronicler.sh |
| FR-MGR-002 | Agent 终端 | what/manager.md §前端页面 | terminal-runtime（sandbox profile，可选隔离沙箱，ADR-0021） | 人工：--profile sandbox up -d 后访问 term.localhost/ui |
| FR-MGR-003 | 代码源管理 | what/manager.md §数据模型 | chronicler/（M2 规划） | 待实现（M2） |
| FR-MGR-004 | 任务多方式触发 | what/manager.md §数据模型 | chronicler/（M2-M3 规划） | 待实现（M3） |
| FR-MGR-005 | 一切皆 Run | what/manager.md §数据模型 | chronicler/app/runner.py（输入快照已冻结；重放/重跑待续） | 人工：查看 Run 输入快照 |
| FR-MGR-006 | SSE 实时日志 | what/manager.md §API 概要 | chronicler/（M2 规划） | 待实现（M2） |
| FR-MGR-007 | 内置六类任务 | what/manager.md §任务类型框架 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-008 | 报告分级可见 | what/manager.md §权限规格 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-009 | 待审闭环 | what/manager.md §数据模型 | chronicler/（M4 规划） | 待实现（M4） |
| FR-MGR-010 | CI 结果消费 | what/manager.md §数据模型 | chronicler/（M5 规划） | 待实现（M5） |
| FR-MGR-011 | Prompt 库版本化 | what/manager.md §数据模型 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-012 | 项目全景仪表盘 | what/manager.md §前端页面 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-013 | 项目影子库 | what/manager.md §数据模型 | chronicler/（M4 规划） | 待实现（M4） |
| FR-MGR-014 | 全局资产库 | what/manager.md §数据模型 | chronicler/（M4 规划） | 待实现（M4） |
| FR-MGR-015 | 资源能力注入（skill 化） | what/manager.md §契约要点 | chronicler/（M2 规划） | 待实现（M2） |
| FR-MGR-016 | 任务来源适配与降级 | what/manager.md §任务类型框架 | chronicler/（M3 规划） | 待实现（M3） |
| FR-MGR-017 | 分角色鉴权与可插拔鉴权后端 | what/manager.md §权限规格 | chronicler/app/auth.py + routers/users.py + routers/oidc.py（local/oidc 双后端，ADR-0023） | scripts/verify-chronicler.sh（401）；scripts/wire-chronicler.sh（oidc 接线） |
| FR-MGR-018 | 全局组件配置 | what/manager.md §数据模型 | chronicler/config/components.yaml + chronicler/app/registry.py | 人工：改 enabled 后观察 prompt 注入变化 |
| FR-MGR-019 | Agent harness 登记（命令模板） | what/manager.md §数据模型 | chronicler/config/harness.yaml + chronicler/app/runner.py（ADR-0021） | 人工：登记 harness 后触发 Run |
| FR-MGR-020 | 工程实体与配置覆盖 | what/manager.md §数据模型 | chronicler/app/projects.py | 人工：建工程+覆盖项触发 Run |
| FR-MGR-021 | 工程分析策略配置 | what/manager.md §任务类型框架 | supervisor（M3 规划） | 待实现（M3） |
| FR-TASK-001 | 任务前端提交 | what/task-mgmt.md §角色分工 | docker-compose.yml(requirements profile) | 人工：建包后 API 检索 |
| FR-TASK-002 | AI 任务领取 | what/task-mgmt.md §API 契约 | .agents/skills/openproject/（Manager M2 起自动化） | 人工：按 skill 领任务置 in progress |
| FR-TASK-003 | AI 状态回写 | what/task-mgmt.md §状态机 | .agents/skills/openproject/ + OpenProject workflow 配置 | 人工：回写成功且置 closed 被拒 |
| FR-TASK-004 | 任务↔提交关联 | what/task-mgmt.md §关联契约 | 提交信息约定 OP#<id> | 人工：抽查提交↔工作包互查 |
| FR-TASK-005 | 任务手工导出快照 | what/task-mgmt.md §关联契约 | scripts/export-openproject.sh | 人工：运行脚本看 INDEX.md |

## 非功能需求（NFR）

| 需求 ID | 标题 | 落实位置 | 验证 |
|---------|------|---------|------|
| NFR-001 | 全免费含商用 | why/licensing.md；镜像选型；Docker Desktop 可选路径注记（ADR-0020） | 人工：license 清单核查 |
| NFR-002 | 密钥不落明文 | .env.example / .gitignore；chronicler harness env ${VAR} 引用（ADR-0021/0023） | 仓库检索 + 人工核查 |
| NFR-003 | 资源可控/按需启停 | docker-compose.yml profiles | `docker compose ps` 按 profile |
| NFR-004 | 一键部署可验证 | scripts/*.sh + README | scripts/verify.sh |
| NFR-005 | 构建可复现 | images/*/Dockerfile 版本锁定 | 重建比对 digest |
| NFR-006 | 三形态同源 | scripts/build-images.sh + 封装脚本；supervisor 独立交付（ADR-0020，待实现） | 人工：封装脚本复用 compose |
| NFR-007 | Agent 成本可控 | chronicler harness 注册表 + Ollama profile | 人工：切换本地模型跑任务 |
| NFR-008 | 数据显式持久化 | docker-compose.yml bind mounts（${DATA_ROOT:-./data}）；scripts/backup.sh + restore.sh（ADR-0015） | `down`+升级+`up` 后数据完整 |
| NFR-009 | 系统数据 Git 化 | docs/、knowledge/vault/、jenkins/casc.yaml（已落实）；scripts/export-openproject.sh（手工导出，ADR-0014）；chronicler Git 落盘（M3 起） | 抽查数据可定位 Git 事实源 |
