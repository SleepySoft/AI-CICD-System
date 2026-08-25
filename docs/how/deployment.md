# 部署与交付机制

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：环境的交付形态与部署机制（WHY/WHAT 摘要见 ../why/vision.md、../what/environment.md）；操作步骤见 ../runbooks/deploy.md
> 关联需求：NFR-003、NFR-004、NFR-006

## 1. WHY / WHAT 摘要

Docker Compose 是唯一事实源（原则 1），WSL/VM 镜像只是封装。服务清单、域名、profile、资源分档等契约见 ../what/environment.md。

## 2. HOW

### 2.1 交付形态

```
仓库根/
├── docker-compose.yml      # 核心编排（profiles 按需叠加）
├── .env.example            # 全部可调参数
├── images/                 # 各工具链 Dockerfile
└── scripts/                # 构建/接线/验证脚本
    ├── build-wsl（规划）    # Compose 就绪后导出 rootfs tar，wsl --import 即用
    └── build-vm（规划）     # Packer + cloud-init 构建 VM 镜像（复用同一 compose）
```

WSL/VM 封装**复用同一 compose**，不允许出现独立配置副本（NFR-006）。

### 2.2 启动与接线机制

1. `docker compose up -d` 起核心栈，依赖 healthcheck 排序；Keycloak 健康端点在 **9000** 端口。
2. 预置 realm 自动导入（keycloak/realm/），含 dev/boss 组与 OIDC 客户端。
3. 接线脚本完成运行时注册：`wire-sso.sh`（Gitea↔Keycloak + Gitea 管理员）、`wire-manager.sh`（Manager 客户端）。
4. 验证脚本冒烟：`verify.sh`（环境）、`verify-manager.sh`（Manager）、`check-kc.sh`（Keycloak）。

### 2.3 profile 机制

重负载/可选组件挂 profile（knowledge/requirements/monitor/localai/browsers），核心栈默认最小可运行（NFR-003）。Android 模拟器依赖 KVM，WSL 下默认不启用。

### 2.4 安装器（规划）

aisys-installer（Python/Textual TUI + FastAPI 管理页）：环境探测 → 组件勾选（profile）→ 域名/端口/管理员/LLM Key 收集 → 分步部署（失败给原因与修复建议，断点续装）→ 冒烟测试 → 打印访问清单。

## 3. 决策与备选

| 决策点 | 选择 | ADR |
|--------|------|-----|
| 反向代理 | Caddy（自动 HTTPS、配置极简） | 无（无被认真考虑的备选，未达 ADR 阈值） |
| 门户 | Homepage | 无（Heimdall 为等价备选，无否决性差异） |
