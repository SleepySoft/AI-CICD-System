# Runbook: Outline 加载与认证故障排查

> 版本：v1.0 · 日期：2026-09-27 · 状态：生效
> 适用：宿主 PowerShell、Docker 可用；Outline 已部署
> 定位：定位入口失败和加密认证字段故障；不包含数据清空或无备份的密钥轮换
> 关联：FR-ENV-003；[组件测试](testing.md)、[秘密库](vault.md)

## 目的

区分入口不可达、服务启动失败和单个账号认证数据不可解密。容器 healthy、首页 HTTP 200
或测试账号能登录，都不足以证明其它账号正常。

## 步骤

1. 在仓库根的 PowerShell 检查入口、状态和启动错误：

   ```powershell
   curl.exe --noproxy '*' -I http://kb.localhost
   docker ps -a --filter name=outline --format "{{.Names}} {{.Status}}"
   docker logs --tail 80 aisystem-outline-1
   ```

   502 表示当前代理上游不可用，结合容器状态与日志定位；首页 200 后还需检查登录后的 API。
   日志中 `Failed to decrypt database column (jwtSecret)` / `bad decrypt` 表示当前
   `SECRET_KEY` 无法解密已有账号认证字段。
2. 运行组件自带的只读诊断，不输出密钥或令牌：

   ```powershell
   $env:PYTHONUTF8='1'
   chronicler\.venv-win\Scripts\python.exe chronicler/components/outline/hooks/auth_health.py
   ```

   `ok: true`、所有 `failed: 0`、退出码 0 表示受检查字段均可解密；退出码 1 表示已定位
   无法解密的字段，`affected_users` 列出受影响账号；退出码 2 表示诊断本身未完成。
   脚本检查当前 Outline AES-256-CBC 格式的认证字段，不检查文档协作状态的二进制内容。
3. 对照 [秘密漂移审计](testing.md)。容器与秘密库一致仍可能存在历史数据密钥不匹配。
   若一部分账号通过、另一部分失败，不要直接全局回退密钥，否则可能破坏后来创建的账号。
4. 优先查找原始 `OUTLINE_SECRET_KEY` 与对应备份，验证原密钥可解密受影响字段后，
   才规划迁移到当前密钥。不要把密钥贴入聊天、日志或 Git。
5. 原密钥无法恢复时，先将目标账号与 OAuth 认证记录做加密备份，并验证备份可解密。
   本地恢复包放在 `secrets/outline-recovery/`（Git 忽略），使用秘密库主密钥加密。
   重建认证数据前确认受影响账号及旧会话、令牌失效的影响；账号、权限与文档无需删除。

## 验证

- 修复后重跑第 2 步，所有认证字段 `failed: 0`。
- 受影响账号从 Outline 的 SSO 入口重新登录，确认页面和文档列表正常，API 不再返回 500。
- 按 [生产登录巡检](testing.md) 验证 OIDC 全链路。该巡检使用 `dev` 测试账号，不能替代
  对受影响账号的验证。

## 常见问题

| 现象 | 实测原因 | 处置 |
|------|----------|------|
| `dev` 登录正常，旧 `boss` 页面加载失败 | 2026-09-27：当前密钥可解密新账号，但旧账号的 jwtSecret、accessToken、refreshToken 均失败 | 按上述步骤备份与恢复目标账号认证数据，勿全局回退密钥；见 AGENTS.md 已知环境坑 |
| 容器 healthy，但登录后的请求触发退出 | 认证字段解密失败导致 Outline fatal 错误 | 检查全部账号的加密字段，而不是只测试首页 |

## 回滚

只读诊断无需回滚。认证修复若需回滚，使用已验证的加密恢复包，在事务中恢复目标账号的
原始认证字段，并核对账号 ID 与记录 ID。恢复旧密文只能撤销修改，不能解决缺失旧密钥的故障；
回滚前先保留修复后的备份，避免覆盖新增认证状态。
