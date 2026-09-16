# 秘密库与组件密钥对接设计

> 版本：v2.0 · 日期：2026-09-16 · 状态：生效
> 定位：秘密库（vault）与组件密钥体系的对接架构；不含 UI 细节
> 关联：[ADR-0039](../adr/0039-reinit-recover-over-fresh.md)、[ADR-0040](../adr/0040-secret-reexport-and-reset-policy.md)、
> [ADR-0041](../adr/0041-secret-snapshot-and-master-key.md)、[ADR-0044](../adr/0044-recipient-key-hierarchy.md)、
> **ADR-0045**（糊化 .env + 使用时渲染，已推翻本文 v1 的双写模型）；操作见 [runbooks/vault.md](../runbooks/vault.md)

## 1. 现状盘点（v2，ADR-0045 后）

- **vault 是唯一静态事实源**：`.env` 秘密字段为 `VAULT:<scope>/<KEY>` 糊化引用（启动时自动迁移存量明文）；
  非秘密配置（端口/域名/时区）照常明文。
- **使用时渲染**：每次部署/能力调用现场从 vault 解密渲染临时 env（0600，用完即删）
  ——见 `tools.py:_render_env_if_masked` / `component_exec._resolved_field_env`；锁定时 fail-closed。
- **消费层**：组件容器 env（部署时冻结）+ 组件内部凭据库（如 gitea 认证源，由 initialize 钩子写入）。
- **防线**：`scripts/audit-secret-drift.py`（容器 env vs vault 哈希对比）、`scripts/verify-auth.py`
  （逐组件可达+可登录巡检）、initialize 钩子幂等自愈（漂移时覆盖更新，如 gitea 认证源 update-oauth）。

> 以下为 v1 对接模型的设计推演记录，其中「双写」「vault 不改写 .env」「轮换不联动」三条
> 已被 ADR-0045 推翻（见 §2 决策表标注）；主密钥生命周期（§4）与锁定语义仍然有效。

## 1. 现状盘点

两条已存在但互不相通的秘密链路：

- **组件密钥链**：向导生成/收集秘密 → `config_store._secrets` 进程内暂存 →
  `persist()` 原子写 `.env`（白名单 = `GLOBAL_KEYS` + 组件 `setup.yaml` 声明字段）→
  compose 注入容器。`.env` 是组件运行的唯一事实，但无审计、无灾备、不可管理。
- **秘密库链（vault 一期已实现）**：admin 手工登记的秘密 → age 密文存 `vault_secrets` 表 →
  审计 + 全量导出 + 本地验证。组件秘密目前不在其中——**主密钥 + 导出包无法重建 `.env`**，
  ADR-0041 的"防丢"承诺对组件秘密尚未兑现。

对接目标：组件秘密纳入 vault 的管理、审计与灾备，`.env` 保持 compose 注入的工作层地位不变。

## 2. 对接模型：三层职责

```
┌─ 管理层  vault（chronicler.db，age 密文）：管理事实源 + 审计 + 导出灾备
│     ↑ 双写（persist/导入）        ↓ 仅显式恢复时反向
├─ 工作层  .env（宿主明文，chmod 600）：compose 注入的运行事实
│     ↓ docker compose env 注入
└─ 消费层  组件容器（hook 以 .env 为准对齐现实，ADR-0039）
```

事实源方向：**写入走双写（vault 与 .env 同时更新），日常以 vault 为管理视图；
vault/恢复链路对 `.env` 永远只读**——`.env` 的唯一写入者是初始化向导的 `persist()`，
恢复时程序通过导出/解出/显示把值交给用户，由用户在向导重填或手工放置，程序主体
不改写 `.env`、不做任何数据清理操作。vault 不取代 `.env`——compose 注入要求
`.env` 保持宿主明文，这是物理约束。

**旧数据锁定语义**：启动或打开秘密库时发现 vault 中已有秘密但主密钥缺失或解密校验
失败，进入**锁定（locked）**状态——页面提示存在既有秘密数据并要求输入解锁密钥
（admin 粘贴 `AGE-SECRET-KEY-...`，系统抽样解密验证通过后写入 `secrets/master.key`）。
绝不静默生成新主密钥（否则旧数据无声变砖）。用户若确要全新开始：停止程序后手工清理
（删除 vault_secrets 记录与 secrets/ 目录）再重启，程序内不提供任何清空入口。

### 决策与备选

| 决策点 | 选择 | 备选与否决原因 |
|--------|------|---------------|
| 谁是权威 | **ADR-0045 后：vault 唯一静态事实源**（v1：双写，已被推翻） | v1 双写：.env 明文即泄漏面，2026-09-16 漂移事故实证双写无法保持一致 |
| vault→.env 方向 | **ADR-0045 后：vault 糊化 .env（VAULT: 引用），使用时渲染**（v1「永不改写」已推翻） | v1 的顾虑（程序改写运行事实）由「迁移可审 + 锁定期不迁移」化解 |
| 已有秘密 + 主密钥缺失/不匹配 | 锁定并询问解锁密钥，抽样解密验证通过后收养该密钥 | 静默生成新主密钥：旧秘密无声变砖，违背“不能不透明、丢了都不知道”（用户明确否决） |
| 全新开始 | 程序外手工清理（删 vault_secrets + secrets/）后重启；程序不提供清空入口 | 程序内一键清空：不可逆操作不应出现在管理界面（同 ADR-0038/0039 反破坏立场） |
| scope 映射 | scope=组件名（共享/底座用 `infra`），name=ENV_KEY | 全部塞 `infra`：丢失组件维度，二期 scope ACL 无法按组件授权 |
| 漂移检测 | 启动与预检时对比 `.env` 值与 vault 登记的明文 sha256，不一致标"漂移"，admin 手工确认后重新导入 | 自动以 .env 覆盖 vault：会把运维手工改动静默吞掉，且丢失"何时漂移"的审计点 |
| 哪些键进 vault | `setup.yaml` 中 `kind: secret` 的字段 + `GLOBAL_SECRET_KEYS` | 非秘密键（TZ/BASE_DOMAIN 等）不进：vault 只管秘密；`INIT_ADMIN_*` 不进：管理员口令只存哈希，可重置（ADR-0040） |
| vault 侧轮换是否联动运行容器 | **轮换只写 vault（单点）；传播靠再部署收敛**：重新部署时 compose 按配置哈希自动重建容器拿新值（含 `ensure_running` 的 stopped 路径——已修复其 docker start 不渲染的缺口）；组件内部凭据由 initialize 钩子幂等自愈 | 轮换即自动全量重建：blind restart 生产组件风险大；收敛时机应交给人 |

## 3. 同步规则

1. **双写点**：`config_store.persist()` 是所有秘密落 `.env` 的唯一漏斗。persist 成功后，
   把本次写入的 secret 键（`kind: secret` 字段 + 全局秘密键，排除 `INIT_ADMIN_*`）逐条
   upsert 进 vault：`scope=字段所属组件名`（全局键归 `infra`），`secret_type`/`rotation_risk`/
   `summary` 直接沿用 setup.yaml 字段自述——核心不新增任何组件知识。
   bootstrap 模式下 `db.init()` 幂等补表后双写（normal 模式表已存在）。
2. **导入（老系统接管）**：`POST /api/vault/import-env`（admin，写审计）——按
   `configured_presence` 同款解析读现有 `.env`，把已配置的秘密键导入 vault（已存在且
   值相同跳过；值不同标记冲突，不覆盖，由 admin 确认）。解决"vault 空、.env 满"的存量接管。
3. **漂移检测**：vault 每条记录存有明文 sha256；启动/preflight/秘密库页加载时对 `.env`
   中同键值算 sha256 对比——vault 有记录但 `.env` 缺失 → "缺失"；sha256 不一致 → "漂移"。
   页面标记，处置动作 = 重新导入（以 .env 为准）或在 vault 侧改回。
4. **审计**：双写、导入、漂移处置分别记 `vault.sync` / `vault.import_env` / `vault.drift`，
   永不含值（沿用现有红线）。
5. **锁定与解锁**：`crypto.ensure_identity()` 只在 vault 无任何秘密时允许生成新主密钥；
   vault 非空而主密钥缺失 → 抛 Locked 状态而非生成。`POST /api/vault/unlock` 接收 admin
   提交的主密钥，对库存秘密抽样解密验证：通过则写入 `secrets/master.key`（chmod 600）
   并记 `vault.unlock` 审计；不匹配则拒绝且不落盘。解锁入口只出现在锁定状态。

## 4. 主密钥生命周期：生成、交接、持有、丢失、轮换

秘密进 vault 后，admin 的密钥从哪来、怎么拿、丢了怎么办——这是闭环的最后一环：

| 阶段 | 机制 |
|------|------|
| 生成 | 首次写入秘密时服务端自动生成 age 密钥对（非人想密码）；初始化双写触发时生成并进向导完成页交接；存量系统首次使用秘密库时生成 |
| 交接（强制） | 生成后 vault 处于“未交接”状态：秘密库页持续警示横幅；admin「显示主密钥」转存后须**粘贴回验证**（prove possession）才解除；交接状态持久化，写审计 `vault.key_acked` |
| 日常持有 | admin 无需手持密钥：服务端持 master.key 代为加解密，admin 凭 Web 会话操作；主密钥只用于灾备与离线验证 |
| 副本 | 密码管理器 + 至少一份物理隔离离线副本；主密钥永不入导出包（密钥与密文分离） |
| 丢失 | master.key 丢失 → 锁定（§3.5 解锁）；所有副本皆失 = 全部不可恢复——单点即主密钥本身，靠交接强制与副本纪律对冲 |
| 轮换 | 主密钥泄漏或持有 admin 离职 → 生成新密钥对、全部密文重加密、重新交接（P2） |
| 多 admin | 一期共享同一主密钥（「显示主密钥」均可及，全部审计）；二期按 ADR-0044 演进每主体密钥对 |

为什么不让 admin 自设密钥：自提供允许弱密钥/复用旧口令；服务端 256 位随机生成 + 强制交接
既安全又可闭环。备选“用户口令包裹主密钥”否决：口令遗忘与主密钥丢失等价，未减少单点。

## 5. 推演

### 5.1 全新初始化（greenfield）

向导收集秘密 → `persist()` 原子写 `.env` → 同一事务点后双写 vault（每条 `scope=组件名`）→
审计链：`setup.persist` + N 条 `vault.sync`。admin 打开秘密库即可看到全部组件秘密的元数据；
「全量导出」得到 manifest（哪些组件有哪些密钥）+ payload.age（全部值）→ 主密钥转存密码管理器。
**防丢闭环达成**：master.key + 导出包 = 完整重建能力。

### 5.2 老系统接管（vault 空、.env 满）

升级后 admin 进入秘密库 → 页面提示"检测到 `.env` 中 N 个组件秘密未纳入管理" →
点「从 .env 导入」→ 逐条 upsert（审计 `vault.import_env count=N`）→ 此后导出包即覆盖组件秘密。
本次环境（2026-09-04 事故后的现状）就走这条路径。

### 5.3 主密钥缺失/不匹配（锁定与解锁）

master.key 丢失但 chronicler.db 中仍有秘密 → 秘密库页显示锁定横幅（既有 N 条秘密、当前
密钥不可解）→ admin 从密码管理器取回 `AGE-SECRET-KEY-...` 粘贴到解锁对话框 → 抽样解密
验证通过 → 写入 master.key，一切恢复。若 admin 确实没有旧主密钥：页面指引“停止程序，
手工删除 data/private/chronicler 中 vault 数据与 secrets/ 目录后重启”——程序不代办。

### 5.4 主机丢失灾难恢复

新机器装 Chronicler → 空库状态下在秘密库页用旧主密钥**解锁**（unlock 收养该密钥）→
「从导出包恢复」上传最近的导出包 → 全部秘密（含元数据与 sha256 校验）回到 vault →
重跑初始化时在向导中按恢复出的值逐项重填（或手工放置 `.env`）→ recover 收敛（ADR-0039）
→ 组件 hook 以 .env 为准对齐现实。程序不自动生成或改写 `.env`，但全程不需要记得任何
一个具体密码——查导出包即可。

### 5.5 凭据漂移排查（两种实测形态）

- **2026-09-04 形态（.env 时代）**：组件 hook 报认证失败 → 秘密库查该组件条目：sha256 与 `.env` 一致但组件拒绝
  → 结论"组件内凭据被改" → admin 「显示」取值 → 按 ADR-0040 路径在组件侧对齐或重置。
- **2026-09-16 形态（ADR-0045 时代）**：SSO 登录失败但 vault/.env 自洽 → `scripts/audit-secret-drift.py`
  发现**容器 env 与 vault 漂移**（部署后未重建 + 初始化时代占位秘密残留）→ 对齐路径：回填 vault
  或按 vault 渲染重建容器 → `scripts/verify-auth.py` 验证登录链恢复。教训：**漂移检测必须覆盖到
  容器层**，只看 .env ↔ vault 两端不够（组件内部凭据库如 gitea 认证源是第三份拷贝，靠 initialize
  钩子幂等自愈兜底）。

### 5.6 口令轮换（当前形态）

admin 在秘密库改值（唯一写入点）→ 快照自动重写 → **重新部署相关组件**（工具面板「部署」或下次
autostart 的 compose up）使容器拿到新值 → 组件内部凭据（如 gitea 认证源）由 initialize 钩子覆盖对齐
→ `scripts/verify-auth.py` 验证登录链。界面提示与审计照旧。

### 5.7 组件新增/移除

新增组件：setup.yaml 声明的 secret 字段进入白名单 → 首次 persist 后条目出现在 vault；
预检可报"组件 X 声明的秘密未配置"。组件移除：vault 条目保留（历史与导出仍可见），
标记属主组件已卸载——秘密不因组件删除而静默消失。

## 6. 数据映射

| .env / setup.yaml | vault 条目 |
|---|---|
| 字段 `key`（如 `GITEA_ADMIN_PASSWORD`） | `name` |
| 字段所属组件 | `scope`（全局键 → `infra`） |
| `secret_type` / `rotation_risk` / `help` | 同名直传 / `summary` |
| 值 | `ciphertext`（age）+ `sha256` + `size` |
| — | `owner`（默认组件名，可改）、`expires_at`（手工补登） |

`UNIQUE(scope, name)` 约束天然支持多组件同名键不冲突（如各自的 `*_ADMIN_PASSWORD`）。

## 7. 实现拆分

- **P1（对接闭环）**：persist 双写（含 bootstrap 下幂等补表）→ `import-env` 端点与
  秘密库页入口 → 漂移检测与标记。约 200 行 + 测试（双写一致、导入幂等、漂移检出、
  审计无值）。完成后 ADR-0041 的防丢承诺对组件秘密兑现。
- **P2（联动）**：vault 轮换联动 .env + 组件 hook 对齐（ADR-0040 口令重置路径）；
  向导内"从 .env 导入"步骤；`.env` 变化的文件监听自动提示。
- **P3（多接收者）**：ADR-0043/0044 的 scope ACL、提交即加密、CI 内解密注入。

## 8. 边界（本设计不做）

- vault 是渲染来源但**永不回写明文 .env**；程序主体不做任何数据清理操作，全新开始只能程序外手工删除。
- 不存 `INIT_ADMIN_*` 与非秘密配置键；不接管组件运行时内部凭据（组件自己持有的 token）。
- 轮换不做自动全量重建（收敛时机由人控制）；导出包仍是灾备制品；vault 数据库本身不含可独立恢复的明文。
