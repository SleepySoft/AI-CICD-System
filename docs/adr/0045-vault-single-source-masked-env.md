# ADR-0045 vault 为唯一静态事实源：糊化 .env、使用时渲染、轮转单点写入

> 日期：2026-09-05 · 状态：已接受
> 关联：[ADR-0041 主密钥+快照](0041-secret-snapshot-and-master-key.md)（.env 恢复角色被本文取代）；[ADR-0040 再导出与重置](0040-secret-reexport-and-reset-policy.md)；[ADR-0039 恢复式收敛](0039-reinit-recover-over-fresh.md)；[ADR-0044 多接收者密钥体系](0044-recipient-key-hierarchy.md)；设计推演见 [how/secrets-vault.md](../how/secrets-vault.md)

## 背景

- 现状下宿主存在多处明文秘密驻留：`.env`（磁盘）、`secrets/master.key`（磁盘）、容器 env
  （docker inspect 可见）。人类口令已只存哈希（正确），但组件间交互凭据本质必须能产出明文，
  无法哈希——工程上只能缩小明文驻留面、收紧访问、全程审计。
- ADR-0039/0041 曾把 `.env` 当作组件秘密的声明事实源与灾难兜底；vault 一期落地后，
  继续保留 `.env` 明文会让"唯一事实源"模糊化：轮转后 `.env`、vault、组件内部、容器 env
  多份拷贝难以准确同步。

## 决策

1. **vault 是全部组件秘密的唯一静态事实源**（密文）；`.env` 糊化——非秘密配置（端口/域名/
   时区等）照常保留，秘密字段改写为占位引用 `VAULT:<scope>/<KEY>`。`.env` 不再是秘密载体，
   仍可入库审查结构。
2. **使用时渲染**：supervisor 在执行 compose 或 hook 前，从 vault 解密渲染临时完整 env
   （临时文件 0600 或进程内注入，用完即删）；组件容器与 hook 的注入机制不变，仅来源切换。
3. **轮转单点写入**：秘密只能在 vault 变更（唯一写入点，全审计）；传播链为——系统通道
   （hook check-apply 对齐 + 容器重建）、在线取用即时生效、快照通道（每次变更自动重写
   `secrets/secrets.age`）。糊化 .env 是静态占位，不参与同步。
4. **再次初始化/恢复从 vault 回填**：向导的已配置判定与取值改读 vault（引导会话/admin 身份），
   不再依赖"留空保持 .env"。
5. **主密钥跨平台存储**：优先进入 OS 钥匙串（Windows DPAPI / macOS Keychain / Linux
   libsecret，经 `keyring` 库），无钥匙串环境回落 `secrets/master.key`（chmod 600）；
   灾备副本仍是密码管理器中的明文 `AGE-SECRET-KEY`。
6. 人类口令维持"只存哈希"（Chronicler 本地 admin）或"组件内自管"（组件 admin），不变。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持 .env 明文 + 多拷贝同步 | 轮转后一致性无法保证；正是本文要消除的问题（用户明确提出） |
| 删除 .env 文件 | 丢失结构文档价值；糊化版保留非秘密配置与变量清单，仍可被 compose 引用（占位符会在渲染时替换） |
| 启动口令解锁（Vault unseal 模式） | 与无人值守自启冲突：重启后系统等待人工输密码，CI 全停 |
| 自建各平台钥匙串封装 | `keyring` 库成熟且后端齐备，无自研必要 |

## 后果

- 正面：磁盘上无永久明文秘密文件，宿主明文收敛为"主密钥（可被钥匙串绑定）+ 容器 env
  （compose 模型残余面，docker inspect 可见，属可接受残余）"。
- 正面：轮转一致性由"单点写入 + 派生再生"保证，不存在多拷贝互相同步。
- 负面（必须兑现）：灾备链变为"导出包/快照 + 主密钥"单链——**每次 vault 变更自动重写
  `secrets.age` 从建议升级为强制**；`.env` 不再兜底。
- 负面：初始化向导、persist、compose 执行、hook 注入、漂移检测（翻转为 vault vs 组件现实）
  均需改造；手动 compose 运维须先渲染临时 env（runbook 更新）。
- 同步更新：`what/initialization.md`、runbook（vault/deploy）、AGENTS.md、追溯矩阵。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
