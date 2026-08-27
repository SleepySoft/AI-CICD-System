# 非功能需求（NFR）

> 版本：v1.1 · 日期：2026-08-27 · 状态：生效
> 定位：质量属性与横切约束。`[一票否决]` 项是选型的前置过滤条件，违反即淘汰。

### NFR-001 [一票否决] 全部组件免费（含商用）
- 状态: 生效 | 上层: - | 优先级: P0
- 描述: [一票否决] 环境内所有软件组件须免费且允许商用，授权须为 OSI 许可或官方明确商用免费。
- 验收: 组件清单逐一核查授权（背景见 `../why/licensing.md`）；已知风险项（Anaconda/defaults 通道）被排除并有替代；Docker Desktop 仅作为用户自带许可的可选 docker 运行时，默认路径（WSL/原生 dockerd）保持免费（决策见 `../adr/0020-manager-out-of-docker-supervisor.md`）。

### NFR-002 密钥不落明文、不入库
- 状态: 生效 | 上层: - | 优先级: P0
- 描述: 仓库内只提交 `.env.example`；运行时密钥存 Docker secret、supervisor 进程环境变量（`harness.yaml` 的 `${VAR}` 引用，ADR-0021）或加密列。supervisor v1 本地账密后端（ADR-0023）仅限内网/单机使用，暴露公网必须换 OIDC 后端。
- 验收: 仓库全文检索无真实密钥；注册表/配置中密钥只出现 `${VAR}` 引用名；公网部署走 OIDC。

### NFR-003 资源占用可控、组件按需启停
- 状态: 生效 | 上层: UR-001 | 优先级: P0
- 描述: 核心栈可在 4C/8G/60G 运行；重负载组件（Android 构建等）经 profile 按需启用。
- 验收: core profile 在 4C8G 机器启动并通过冒烟；Android 相关服务默认不启动。资源分档见 `../what/environment.md`。

### NFR-004 一键部署、断点续装、冒烟可验证
- 状态: 生效 | 上层: UR-001 | 优先级: P0
- 描述: 部署脚本带错误反馈；失败可续装；每组件有健康检查与冒烟验证。
- 验收: 全新机器按 README 操作可完成部署；`scripts/verify.sh` 全绿。

### NFR-005 构建环境可复现
- 状态: 生效 | 上层: UR-002 | 优先级: P0
- 描述: 工具链镜像全部 Dockerfile 版本锁定并推送内部 registry。
- 验收: 重建镜像 digest 可复现；镜像 tag 与 Dockerfile commit 对应。

### NFR-006 三种交付形态同源
- 状态: 生效 | 上层: UR-001 | 优先级: P1
- 描述: Docker Compose 是容器栈的唯一事实源；WSL rootfs 与 VM 镜像只是其封装，不单独维护配置。supervisor（Manager 宿主形态，决策见 `../adr/0020-manager-out-of-docker-supervisor.md`）独立于 compose，作为第二交付件由平台原生服务管理器托管。
- 验收: WSL/VM 镜像构建脚本复用仓库内 compose，无独立配置副本；supervisor 有独立安装器/服务注册，不侵入 compose 配置。

### NFR-007 Agent 调用成本可控
- 状态: 生效 | 上层: BR-002 | 优先级: P2
- 描述: LLM 接入走 OpenAI 兼容抽象层，云端/本地 Ollama 可切换；embedding 默认本地化。
- 验收: 不配置云端 Key 时，报告类任务可切换本地模型完成（质量降级但可用）。

### NFR-008 数据显式持久化，升级不丢数据
- 状态: 生效 | 上层: - | 优先级: P0
- 描述: 所有服务持久化数据经 bind mount 显式落到宿主磁盘目录（`${DATA_ROOT:-./data}/<服务名>`）；镜像升级、容器重建、编排变更不得影响数据；禁止命名卷存业务数据。
- 验收: compose 中无业务数据命名卷；`docker compose down` + 镜像升级 + `up -d` 后数据完整；数据目录可在宿主直接查看（决策见 `../adr/0012-data-on-host-bind-mounts.md`）。

### NFR-009 系统数据优先 Git 管理
- 状态: 生效 | 上层: - | 优先级: P1
- 描述: 可文本化的系统数据（配置、文档、需求、Prompt、报告、知识、任务/运行元数据）以 Git 仓库为事实源；DB 与二进制存储仅作可重建或可导出回 Git 的运行时层。
- 验收: 抽查各类数据可定位到 Git 事实源或其导出物；DB 型服务丢失后可从 Git 恢复或重建（决策见 `../adr/0013-git-managed-system-data.md`）。
