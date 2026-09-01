# ADR-0031 Web 终端目标选型：宿主 sshd（Windows 自带安装脚本，其它平台用户保证）

> 日期：2026-09-01 · 状态：已接受
> 关联：ADR-0030、chronicler/components/sshwifty/、scripts/setup-ssh-server.ps1、docs/runbooks/web-terminal.md；需求 FR-MGR-024、UR-010

## 背景

SSHwifty（P0）需要一个 SSH 目标。考察：

- **agent 在宿主机**：harness.yaml 实测证据（kimi 为 Windows 原生 Python 应用，注释"Windows GBK 控制台会炸"），工作区也在宿主（data/workspace/）→ 目标必须是宿主机 sshd；容器化 devbox 被否决（agent 不在容器里，容器无法驱动宿主 agent）。
- **OpenSSH 是三平台统一标准**：Linux 装包；macOS 自带（Remote Login）；Windows 为可选功能（本机实测：无 sshd 服务、无 sshd.exe、22 未监听）。
- **公司网络拦截 SSH 出口**：浏览器侧无 SSH；sshwifty 容器 → 宿主 sshd 的 SSH 腿在 Docker Desktop 本机网络内（host.docker.internal:22），不穿越公司网络。

## 决策

P0 目标 = 宿主 OpenSSH Server；项目只自带 Windows 安装脚本（scripts/setup-ssh-server.ps1，管理员执行），Linux/macOS 由用户保证（runbook 一行启用）；SSHwifty Preset 指向 host.docker.internal:22，凭据（Windows 密码或生成的后端密钥）由用户连接时输入，**Preset 不携带任何密钥明文**。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| devbox 容器 sshd | agent 在宿主机不在容器，容器无法调用宿主 agent；双环境割裂 |
| Windows 第三方 SSH 服务（Bitvise 等） | OpenSSH 已是官方统一标准，无需引入第三方/商业组件 |
| Preset 内置密钥 | SSHwifty 明确警告 Presets 明文发送给客户端，不得含密钥 |

## 后果

正面：目标与 agent/工作区同宿主，P0 即可在浏览器驱动宿主 agent；三平台只维护一套协议。
负面：Windows 安装需管理员（UAC）且依赖公司策略允许可选功能；宿主 sshd 暴露 22 端口需纳入防火墙/安全基线；P1 Human Terminal 同宿主场景可改用本地 PTY 传输，SSH 仅保留跨机场景。
同步：scripts/setup-ssh-server.ps1、docs/runbooks/web-terminal.md、.env.example（Preset 注释）、README.md、docs/README.md 索引。
