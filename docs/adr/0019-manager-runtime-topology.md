# ADR-0019 Manager 运行拓扑：保持容器化 + 宿主引导器，不整体搬出 Docker

> 日期：2026-08-26 · 状态：已被 ADR-0020 推翻
> 关联：how/manager-architecture.md §2.5（部署形态）；需求 NFR-001、NFR-005、NFR-008、BR-009；ADR-0007、ADR-0012、ADR-0017

## 背景

M1 落地后暴露一个运维脆弱点：**Manager 自身跑在 Docker 容器里，而 Docker 栈的存活依赖 WSL2 VM**。本机实测 WSL2 空闲约 60s 回收 VM（已知环境坑），VM 回收 → dockerd 停 → 包括 Manager 在内的全栈死亡，恢复只能靠人进 WSL 敲命令。由此提出的设想：**Manager 搬出 Docker、常驻宿主（Windows），负责拉起/管理各组件，仅经文件与 API 与容器内工具交互**。

决策时刻已知的约束：

- NFR-001：组件全部免费含商用——本机不用 Docker Desktop（商用付费），用 WSL 原生 dockerd，宿主与容器天然跨两套网络/文件语义。
- NFR-005 / ADR-0012：环境可复现、数据显式落宿主；compose 是唯一事实源，交付形态是"WSL/VM 镜像封装 compose"，自包含。
- ADR-0017 背景已对同类设想做过否决推理（装宿主直接跑：宿主污染、Windows/WSL 环境分裂、密钥扩散、失去容器隔离）——该理由对 Manager 同样成立。
- 网络现状：Manager 走容器内网直连 `keycloak:8080` / `terminal-runtime:18650`；ATR **故意不暴露宿主端口**（安全边界），仅经 Caddy `term.localhost`。
- Manager 现有能力依赖容器身份：docker.sock 挂载控制工具容器启停（FR-MGR-001）；OIDC 回调/站点 URL 锚定 `app.localhost`（Caddy 路由）。
- 路线图 M6 本就规划 Manager 经 Nuitka 打包为独立二进制（BR-009 保密），二进制形态天然可宿主运行——宿主直跑是**未来可选项**而非现在要做的事。
- 已存在 `scripts/up.sh`（一键起栈+接线+验证，幂等），可作引导器的执行载体。

## 决策

**Manager 保持容器化、作为 compose 核心服务，不整体搬出 Docker；允许（且仅限）一个极简宿主引导器**，职责边界为：开机自启 + 检测 WSL/dockerd/栈健康，异常时执行 `scripts/up.sh` 把栈救活。引导器不做任何业务管理——业务管理界面永远是容器内 Manager（app.localhost）。M6 Nuitka 打包落地时，可重评"宿主直跑"作为第二种受支持形态。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Manager 整体搬出 Docker 常驻宿主 | ①跑 Windows：需宿主 Python 环境、`wsl docker ...` 间接操控，环境分裂且违背 ADR-0017 已否决路径；②跑 WSL 宿主：仍被 VM 回收杀死，核心动机未解决。且内网直连（keycloak/ATR）须改为暴露端口或 Caddy 回源宿主，安全边界（ATR 不落宿主端口）被破坏；OIDC/Caddy/依赖全部要改 |
| 维持现状（无引导器） | 管理面随栈同死，WSL VM 回收后恢复全靠人工命令行，正是本次讨论要解决痛点 |
| Docker Desktop 托管栈+宿主 Manager | NFR-001 一票否决：Docker Desktop 商用付费 |
| 引导器内嵌业务管理功能 | 引导器价值恰在于"极简、无依赖、永远能跑"；塞业务功能等于把 Manager 又搬出一次，回到被否决方案 |

## 后果

- 正面：管理面"永活"收益以极低成本获得（引导器≈几十行脚本 + Windows 任务计划）；Manager 保持容器内网直连与 docker.sock 能力，架构零改动；安全边界（ATR 不暴露宿主端口）不变；M6 二进制化后重评通道已留出。
- 负面：docker.sock 挂载进 Manager 容器的自指/提权风险依旧（可后续在 UI 层禁停 manager 自身容器缓解）；引导器是 Windows 侧脚本，不纳入 compose 事实源，需在 runbook 中显式登记。
- 待办：引导器脚本与开机任务（runbook 级，后续落地）；M6 时重评宿主直跑形态。
- 同步：how/manager-architecture.md §2.5 补记拓扑决策与引导器边界、§3 决策表加一行；docs/README.md 索引登记本 ADR。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
