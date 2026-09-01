# ADR-0030 人机 Web 终端（P0：SSHwifty 组件；P1：Chronicler 内置 Human Terminal）

> 日期：2026-09-01 · 状态：已接受
> 关联：requirements/functional/manager.md（FR-MGR-024）、requirements/stakeholder.md（UR-010）、what/environment.md、how/deployment.md、chronicler/components/sshwifty/；ADR-0021（ATR）、ADR-0027（组件目录）

## 背景

产品愿景从"CICD 环境"扩展为"vibe coding 环境"：用户在浏览器里获得交互式终端，进入 Chronicler 受管工程工作区，手动操作/指挥 agent 写代码。约束与考察：

- **公司网络拦截 SSH 出口**：浏览器到系统的任何链路不得出现 SSH；否则用户直接用本地终端即可，Web 终端失去意义。浏览器↔后端只允许 HTTP(S)/WebSocket。
- **ATR 面向 agent**：ATR（terminal-runtime）提供 PTY 会话的 observe/act/wait API 与文字"截图"，其 README 自述 UI 仅供浏览/调试/人类接管，手感不保证——不适合作为人机终端。
- **SSHwifty 考察**（nirui/sshwifty）：Go 后端 + Vue/XTerm.js 前端，浏览器经 WebSocket 与后端通信，后端以 SSH 客户端连目标；配置支持 SharedKey（网页口令）、Presets（预置目标）、OnlyAllowPresetRemotes、Hooks。其"浏览器只走 HTTP/WS"模型满足公司网络约束；SSH 腿只在可信本机网络内（容器↔host.docker.internal / 同 docker 网络），不穿越公司网络。

## 决策

分三阶段：**P0** 以 SSHwifty 作为组件接入（chronicler/components/sshwifty/，caddy 子域名 ssh.localhost），提供浏览器可用的 Web 终端；**P1** 由 Chronicler 内置 Human Terminal（WebSocket + 可插拔传输 + 工程工作区 + prompt/skill 注入 + 鉴权审计），替代 SSHwifty 承担核心能力；**P2** 与 ATR 会话层协同（human takeover、会话共享、危险命令拦截）。全链路约束：浏览器到系统只走 HTTP(S)/WebSocket，任何路径不得要求用户在浏览器侧发起 SSH。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 用户直接用本地终端 | 公司网络拦 SSH 出口，远程/受限场景不可用；Web 入口才能统一鉴权与审计 |
| 直接以 ATR 当人机终端 | ATR 目标是 agent 可观察性（文字截图），README 自述 UI 手感不佳 |
| P1 前自研完整 Human Terminal | 周期长；P0 先用 SSHwifty 快速获得可用终端，再沉淀核心能力 |
| ttyd/Wetty（本地 PTY Web 终端） | 无 SSH 腿，天然符合约束，保留为 P1 的本地传输选项，不取代 P0 对 SSHwifty 的考察 |

## 后果

正面：P0 快速可用；SSHwifty 模型验证"浏览器只走 HTTP/WS"；组件化接入符合 ADR-0027。
负面：SSHwifty 凭据管理有限（SharedKey 单口令、Preset 不得含密码明文）；P0 目标需可达的本地 SSH 端点（本机 OpenSSH/WSL sshd 或后续 devbox 容器）；P1 前无按用户/工程的会话隔离。
同步：requirements/functional/manager.md（FR-MGR-024）、requirements/stakeholder.md（UR-010）、requirements/traceability.md、what/environment.md、README.md、docs/README.md 索引、chronicler/components/sshwifty/、caddy/Caddyfile、.env.example。
