# 追溯矩阵

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：需求 ID ↔ 设计章节 ↔ 实现位置 ↔ 验证手段。Agent 做 gap 分析的输入；改代码必须同步本表。

## 功能需求（FR）

| 需求 ID | 标题 | 设计章节 | 实现位置 | 验证 |
|---------|------|---------|---------|------|
| FR-ENV-001 | Compose 统一编排 | what/environment.md §服务清单 | docker-compose.yml | `docker compose config -q` |
| FR-ENV-002 | 统一域名入口 | what/environment.md §域名契约 | caddy/Caddyfile | scripts/verify.sh |
| FR-ENV-003 | 统一门户导航 | what/environment.md §服务清单 | homepage/config/ | 人工：门户按组显隐 |
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
| FR-MGR-001 | 工具总览面板 | what/manager.md §前端页面 | manager/app/ + manager/tools.yaml | scripts/verify-manager.sh |
| FR-MGR-002 | Agent 终端 | what/manager.md §前端页面 | manager/app/ + terminal-runtime | scripts/verify-manager.sh |
| FR-MGR-003 | 代码源管理 | what/manager.md §数据模型 | manager/（M2 规划） | 待实现（M2） |
| FR-MGR-004 | 任务多方式触发 | what/manager.md §数据模型 | manager/（M2-M3 规划） | 待实现（M3） |
| FR-MGR-005 | 一切皆 Run | what/manager.md §数据模型 | manager/（M2 规划） | 待实现（M2） |
| FR-MGR-006 | SSE 实时日志 | what/manager.md §API 概要 | manager/（M2 规划） | 待实现（M2） |
| FR-MGR-007 | 内置六类任务 | what/manager.md §任务类型框架 | manager/（M3 规划） | 待实现（M3） |
| FR-MGR-008 | 报告分级可见 | what/manager.md §权限规格 | manager/（M3 规划） | 待实现（M3） |
| FR-MGR-009 | 待审闭环 | what/manager.md §数据模型 | manager/（M4 规划） | 待实现（M4） |
| FR-MGR-010 | CI 结果消费 | what/manager.md §数据模型 | manager/（M5 规划） | 待实现（M5） |
| FR-MGR-011 | Prompt 库版本化 | what/manager.md §数据模型 | manager/（M3 规划） | 待实现（M3） |

## 非功能需求（NFR）

| 需求 ID | 标题 | 落实位置 | 验证 |
|---------|------|---------|------|
| NFR-001 | 全免费含商用 | why/licensing.md；镜像选型 | 人工：license 清单核查 |
| NFR-002 | 密钥不落明文 | .env.example / .gitignore；manager 加密列 | 仓库检索 + 人工核查 |
| NFR-003 | 资源可控/按需启停 | docker-compose.yml profiles | `docker compose ps` 按 profile |
| NFR-004 | 一键部署可验证 | scripts/*.sh + README | scripts/verify.sh |
| NFR-005 | 构建可复现 | images/*/Dockerfile 版本锁定 | 重建比对 digest |
| NFR-006 | 三形态同源 | scripts/build-images.sh + 封装脚本 | 人工：封装脚本复用 compose |
| NFR-007 | Agent 成本可控 | manager LLM 抽象层 + Ollama profile | 人工：切换本地模型跑任务 |
| NFR-008 | 数据显式持久化 | docker-compose.yml bind mounts（${DATA_ROOT:-./data}） | `down`+升级+`up` 后数据完整 |
| NFR-009 | 系统数据 Git 化 | docs/、knowledge/vault/、jenkins/casc.yaml（已落实）；scripts/export-openproject.sh（手工导出，ADR-0014）；manager Git 落盘（M3 起） | 抽查数据可定位 Git 事实源 |
