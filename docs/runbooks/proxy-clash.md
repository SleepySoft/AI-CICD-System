# Runbook: Clash Verge 代理排查（TUN / 系统代理 / DNS / CLI 环境）

> 版本：v0.1 · 日期：2026-09-01 · 状态：生效
> 适用：Windows 本机（Clash Verge Rev + verge-mihomo）；常见症状“开了全局和 TUN 仍不顺畅”
> 关联：AGENTS.md 已知环境坑；docs/runbooks/web-terminal.md（Web 终端会话内 CLI 同用此排查）；docs/runbooks/deploy.md

## 目的

定位“开了全局和 TUN 仍不顺畅”的代理问题并修复：确认 TUN 是否真正接管 L3、出站模式、DNS 路径、CLI 代理环境与节点质量。浏览器能开但 CLI/容器不顺畅，通常不是“没开代理”，而是**只有系统代理生效、TUN 没起来**。

## 诊断步骤（命令均为 PowerShell；实测基准 2026-09-01）

1. TUN 是否真正生效
   ```powershell
   Get-NetAdapter | Select-Object Name, InterfaceDescription, Status
   Get-NetIPAddress -InterfaceAlias '本地连接 2'   # Wintun 网卡名可能不同
   ```
   预期：Wintun 网卡 Status=Up，且地址为 `198.18.x.x`（fake-ip 段）。实测反例：Status=Disconnected、地址只有 `169.254.x.x`（APIPA）→ **TUN 未接管 L3**。
2. 核心以什么模式启动
   ```powershell
   Get-Content "$env:APPDATA\io.github.clash-verge-rev.clash-verge-rev\logs\latest.log" | Select-String 'Starting core'
   ```
   出现 `sidecar mode` = 非服务模式；TUN 需要管理员/服务模式。出现 `service mode` 才正常。
3. 出站模式与代理端口
   ```powershell
   Get-Content "$env:APPDATA\io.github.clash-verge-rev.clash-verge-rev\clash-verge.yaml" | Select-String '^mode:'
   Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' | Select-Object ProxyEnable, ProxyServer
   ```
   期望 `mode: global`（若用户意图全局）；`ProxyServer` 应为 `127.0.0.1:7897`（verge 混合端口）。
4. CLI 代理环境
   ```powershell
   Get-ChildItem Env: | Where-Object Name -match 'PROXY'
   ```
   实测反例：空 → PowerShell 会话里 curl/pip/git/codex 全部直连（直连开发者站会被 403/超时）。
5. DNS 路径
   ```powershell
   Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object ServerAddresses
   nslookup google.com 127.0.0.1
   ```
   若 `nslookup ... 127.0.0.1` 返回 `198.18.x.x`，说明 mihomo fake-ip DNS 可用但系统 DNS 未指向它（实测系统 DNS 为公司 DNS）→ DNS 行为不统一。
6. 节点质量
   ```powershell
   curl.exe -sS -o NUL -x http://127.0.0.1:7897 -w "%{http_code} %{time_total}`n" https://www.google.com
   ```
   实测基准（2026-09-01，走代理）：google 200/3.7s、github 200/3.5s、youtube 200/12.9s、OpenAI 文档 200/16.2s → 慢在节点，与 TUN 无关。

## 修复

1. TUN 真正启用：Clash Verge 设置 → 开启/修复“服务模式”（需管理员），再开关一次 TUN；或右键以管理员身份重启 Clash Verge。验证回到诊断第 1 步（网卡 Up + 198.18.x.x）。
2. 出站模式：UI 把模式切到 Global，确认 `clash-verge.yaml` 的 `mode: global`（rule 模式只有命中规则才走代理）。
3. CLI 代理环境变量（用户级，新开终端生效）：
   ```powershell
   [Environment]::SetEnvironmentVariable('HTTP_PROXY','http://127.0.0.1:7897','User')
   [Environment]::SetEnvironmentVariable('HTTPS_PROXY','http://127.0.0.1:7897','User')
   [Environment]::SetEnvironmentVariable('NO_PROXY','localhost,127.0.0.1,*.localhost,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12,*.lan','User')
   ```
   公司内网（本机 10.30.x 等）必须留在 NO_PROXY，否则内网流量被送代理出口。
4. DNS（可选）：TUN 修好后 dns-hijack 自动接管；不修 TUN 时可在网卡 DNS 手动加 `127.0.0.1`，但公司网络可能有 DNS 策略，谨慎。
5. 节点：换更优节点或订阅；检查“自动切换（主备）”是否选到了慢节点。

## 验证

```powershell
Get-NetAdapter | Where-Object InterfaceDescription -match 'Wintun'   # Status 应为 Up
Get-NetIPAddress -InterfaceAlias '本地连接 2'                        # 应为 198.18.x.x
curl.exe -sS -o NUL -x http://127.0.0.1:7897 -w "%{http_code} %{time_total}`n" https://www.google.com
```

预期输出：Wintun Up + fake-ip 地址；google 200 且 time_total 明显小于修复前实测（3.7s 基准）。

## 常见问题（均为本机实测，2026-09-01）

| 现象 | 原因 | 处置 |
|------|------|------|
| TUN 网卡 Disconnected / 只有 169.254 | 核心以 sidecar 模式启动、非管理员 | 开服务模式 / 管理员重启 Clash Verge（修复 1） |
| curl/pip/git/codex 直连 403 或超时 | 会话无 HTTP_PROXY/HTTPS_PROXY | 设用户级环境变量（修复 3） |
| 浏览器能开但很卡 | 节点质量差或出站非全局 | 换节点；模式切 Global（修复 2/5） |
| 内网访问异常 | NO_PROXY 未含内网段，流量进了代理 | 补 NO_PROXY（修复 3） |

## 回滚

- 环境变量：`[Environment]::SetEnvironmentVariable('HTTP_PROXY',$null,'User')`（HTTPS_PROXY/NO_PROXY 同理）。
- TUN/服务模式：在 Clash Verge 设置中关闭对应开关。

> 注意：本 runbook 不记录节点服务器地址、UUID 等机密；订阅与凭据只存在于用户本机 Clash 配置，不入库。
