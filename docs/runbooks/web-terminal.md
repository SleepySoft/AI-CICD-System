# Runbook: Web 终端（SSHwifty）接入与使用

> 版本：v1.0 · 日期：2026-09-01 · 状态：生效
> 适用：可选底座已起（sshwifty 组件运行中）；P0 目标为宿主 OpenSSH Server（ADR-0031）
> 关联：chronicler/components/sshwifty/、scripts/setup-ssh-server.ps1；需求 FR-MGR-024、UR-010

## 目的

浏览器经 http://ssh.localhost 打开交互式终端进入宿主机，手动操作/指挥宿主上的 agent（aider/kimi…）进行 vibe coding。
链路：浏览器 → caddy(HTTP/WS) → sshwifty → 宿主 sshd（host.docker.internal:22）；**浏览器侧无 SSH**（公司网络拦截 SSH 出口）。

## 前置

- sshwifty 组件已部署：首页工具面板「平台」分组 → 部署；或 `docker compose -p aisystem --env-file .env -f chronicler/components/sshwifty/compose.yml up -d`。
- 宿主 sshd 可达：
  - **Windows（项目自带脚本）**：管理员运行 `scripts\setup-ssh-server.ps1`（安装 OpenSSH Server、自启、防火墙、生成后端密钥、配置 authorized_keys、默认 shell）。
  - WSL/Linux：`sudo apt install openssh-server && sudo systemctl enable --now ssh`（或发行版对应命令）。
  - macOS：`sudo systemsetup -setremotelogin on`。

## 步骤

1. 打开 http://ssh.localhost，输入 `.env` 的 `SSHWIFTY_SHAREDKEY`。
2. Connector：Host `host.docker.internal`，Port `22`，User = Windows 用户名。
3. 认证二选一：
   - 密码：Authentication 选 Password，输入 Windows 登录密码；或
   - 密钥：选 Private Key，粘贴 `data\private\sshwifty\ssh\id_ed25519` 的内容（脚本生成；Windows 管理员公钥认证见常见问题）。

## 验证

```powershell
whoami
Get-Command aider, kimi
```

预期输出：`whoami` 返回本机用户；aider/kimi 均可找到（默认 shell 为 PowerShell，环境与 supervisor 一致）。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| ssh.localhost 打不开 | sshwifty 未部署或 caddy 未重载 | 首页「部署」sshwifty；重启 caddy |
| 连接被拒（connection refused） | 宿主 sshd 未装/未启动 | 管理员跑 `setup-ssh-server.ps1`；`Get-Service sshd` 应为 Running |
| 管理员公钥认证被拒 | Windows OpenSSH 管理员须用 `C:\ProgramData\ssh\administrators_authorized_keys` 且 ACL 仅 SYSTEM/Administrators | 脚本已处理；手工修复：`icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F"` |
| 担心公司网络拦截 SSH | 浏览器侧无 SSH；SSH 腿在 Docker 本机网络内 | 只经 http://ssh.localhost 访问，不要从本地终端 ssh 到外网主机 |

## 回滚

- 停用组件：首页工具面板停止 sshwifty。
- 停用宿主 sshd（Windows）：`Set-Service sshd -StartupType Manual; Stop-Service sshd`；彻底卸载：`Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`。
