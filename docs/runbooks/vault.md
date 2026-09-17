# 秘密库操作手册

> 版本：v1.3 · 日期：2026-09-16 · 状态：生效
> 定位：秘密库（vault）的日常操作、导出验证与灾难恢复；设计依据 ADR-0041~0044
> （多接收者密钥体系为二期，本文仅覆盖已实现的 admin 一期形态）

## 功能入口与模型

Web 界面「秘密库」tab（仅 admin 可见），API 前缀 `/api/vault/*`（全部要求 admin）。

- **值密文、元数据透明**：秘密值一律以 age 密文存储（chronicler.db 的 `vault_secrets` 表）；
  名称、作用域（scope）、类型、用途、属主、过期时间、大小、明文 sha256 全部明文可查——
  admin 永远知道"有哪些秘密、在哪、属于谁、谁能访问"。
- **主密钥**：`<安装根>/secrets/master.key`（chmod 600，永不入库、永不落 data/）。
  可用环境变量 `CHRONICLER_SECRETS_DIR` 覆盖 secrets 目录（测试/特殊部署用）。
- **审计**：所有存取（新增/显示/下载/轮换/删除/导出/查看主密钥）写入审计，
  页面底部「存取审计」可查；审计永不包含秘密值。

## 主密钥保管（最重要的一件事）

主密钥可解开全部秘密，是整个体系的唯一信任根：

1. 首次生成后秘密库页出现“未交接”警示横幅：「显示主密钥」→ 复制 `AGE-SECRET-KEY-...`
   存入密码管理器 → **粘贴回验证**（prove possession）后横幅才解除；
2. 另做至少一份物理隔离的离线备份（U 盘/纸质）；
3. 主密钥 + 主机同时丢失 = 全部秘密不可恢复，只能逐条重置（ADR-0040）。

主密钥文件本身也要随宿主导出/备份策略保护，但它**永不进入 git**（.gitignore 已排除；
`secrets/*.age` 密文快照例外，可入库）。

## 锁定与解锁

系统发现库中已有秘密但主密钥缺失或无法解密时，秘密库进入**锁定**：写入、显示、下载、
导出全部被拒（409），绝不静默生成新密钥。处置：

- 有旧主密钥：粘贴到页面顶部的解锁框，抽样解密验证通过后自动恢复（写审计 `vault.unlock`）；
- 没有旧主密钥：只能停止 Chronicler，**在程序外**删除 vault 数据与 `secrets/` 目录后重启——
  程序主体不提供任何清空入口（ADR-0038/0039 反破坏立场）。

## 组件秘密对接（.env 糊化，ADR-0045）

- **vault 是唯一静态事实源**：`.env` 中秘密字段为 `VAULT:<scope>/<KEY>` 占位引用，非秘密配置
  （端口/域名/时区）照常明文保留；
- **启动自动迁移**：supervisor 启动时发现 .env 仍有明文秘密 → 先导入 vault（以 .env 为准）再糊化；
  库锁定时跳过并告警；
- **使用时渲染**：compose 拉起前从 vault 解密渲染临时 env（0600，用完即删）；hook 注入同理；
  手动运维 compose 时不要直接用糊化的 .env，先渲染：`python -m chronicler env render`（或向
  秘密库页「下载」单条后手工组 env）；
- **自动快照（强制）**：每次 vault 变更自动重写 `secrets/secrets.age`（密文，可入 git）——
  .env 不再是灾难兜底，快照 + 主密钥是唯一恢复链；
- **轮转**：只能在 vault 改值（唯一写入点）；**传播是被动的——轮换后必须重新部署相关组件才生效**
  （工具面板「部署」按钮，或组件停止后下次 autostart 的 compose up；compose 按配置哈希自动重建容器）；
  组件内部凭据（如 gitea 的 OIDC 认证源）由 initialize 钩子幂等覆盖对齐；快照自动重写；
- **验证轮换生效**：`python scripts/verify-auth.py`（逐组件可达+可登录巡检）；
- **漂移检测**：两个层面——秘密库列表「同步」列（.env ↔ vault）；**容器 ↔ vault** 用
  `python scripts/audit-secret-drift.py`（只读哈希对比，漂移退出码 1，适合进巡检/CI）。

## 日常操作

| 操作 | 入口 | 说明 |
|------|------|------|
| 新增文本秘密 | 新增文本秘密 | 名称/作用域/类型/轮换风险/用途/属主/过期时间 + 值 |
| 新增秘密文件 | 新增秘密文件 | 证书、keystore 等，≤10MB；名称留空取文件名 |
| 显示值 | 列表「显示」 | 仅文本型；写审计 |
| 下载 | 列表「下载」 | 文件型取回原始文件；写审计 |
| 编辑 | 列表「编辑」 | 改元数据；文本型可在此轮换值（旧值不可恢复；critical 二次确认） |
| 删除 | 列表「删除」 | 删除后仅存于历史导出包 |

作用域约定：默认与工程名一一对应；`infra`（底座组件）、`signing`（签名资产）为系统作用域。
签名文件的伴随口令（keystore store/key password）应作为同 scope 的文本秘密登记，保证成套恢复。

## 全量导出与本地验证

「全量导出」下载 `vault-export-<时间戳>.tar`：

```
manifest.json   # 明文清单：有什么秘密、属于谁、何时过期、明文 sha256 —— 无需密钥即可浏览
payload.age     # 全部秘密值的 age 密文 tar
README.txt      # 使用说明
```

本地浏览与验证（不依赖 Chronicler 运行）：

```bash
python scripts/vault-inspect.py list    vault-export-*.tar                       # 免密钥浏览清单
python scripts/vault-inspect.py verify  vault-export-*.tar --key secrets/master.key   # 逐条完整性验证
python scripts/vault-inspect.py show    vault-export-*.tar --key secrets/master.key --name signing/upload-keystore --out upload.jks
python scripts/vault-inspect.py extract vault-export-*.tar --key secrets/master.key -d restored/
```

也可直接用标准 age 工具解密：`age -d -i secrets/master.key payload.age > payload.tar`。
导出包是密文，可安全入 git、随备份或异地拷贝；建议每次重要变更后导出一次。

## 灾难恢复

1. 新机器/全新部署：重跑初始化前，先在「秘密库」页用旧主密钥**解锁**（空库时解锁即收养该密钥），
   再点「从导出包恢复」上传最近的 `vault-export-*.tar`——全部秘密（文本+文件+元数据）逐条校验
   后回到库中；同名同值跳过，同名不同值默认不覆盖，确认后以导出包为准。
2. `.env` 重建：恢复出的值在初始化向导重填，或手工放置明文 `.env` 后重启——启动迁移会
   自动导入 vault 并重新糊化（ADR-0045）；组件 hook 以 vault 值为准收敛（ADR-0039）。
3. 导出包可疑损坏：`verify` 不带密钥先验包完整性（payload 摘要），带密钥逐条验明文摘要。
4. 主密钥泄漏：生成新主密钥（删除 `secrets/master.key` 后任意操作触发重建），逐条轮换全部
   秘密值（新密文用新密钥），含 `critical` 标记的按轮换风险提示处置。

## 组件登录故障排查（2026-09-16 事故后新增）

现象：某组件页面能打开但登不上（SSO 跳回登录页 / 账密被拒）。按序排查：

1. `python scripts/verify-auth.py`——全组件「可达+可登录」一键巡检，直接指出断在哪一环
   （SSO 重定向链 / keycloak 认证 / 组件回调 / 会话建立 / 本地账密）；
   另：vault 里改了秘密后，页面顶部会出现黄色「待传播」横幅，列出受影响组件与建议操作
   （重新部署 / 重置密码能力直写），处理完点「已处理，消除」或部署后自动消失；
2. `python scripts/audit-secret-drift.py`——容器 env 与 vault 哈希对比；有漂移 → 重新部署该组件
   （工具面板「部署」），组件内部凭据（gitea 认证源等）重跑对应 initialize 钩子对齐；
3. 仍失败查 AGENTS.md「认证链实测四坑」（系统代理劫持 httpx / keycloak Secure Cookie /
   gitea 注册三开关 / realm 首登动作）——浏览器侧注意系统代理对 *.localhost 的劫持。

已知未决债：postgres 数据库真实密码仍为初始化时代占位值（aisys_pg_change_me 形态），
轮换需协调全部依赖组件（gitea/keycloak/outline/openproject 同窗口重建），单独排期执行。

## 二期预告（未实现）

scope ACL（员工按授权范围在线取密）、接收者密钥对（提交即加密、秘密只在 CI 内解密）、
证书过期主动告警、分发包。设计见 ADR-0043/0044。
