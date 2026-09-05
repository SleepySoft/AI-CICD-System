# 秘密库操作手册

> 版本：v1.0 · 日期：2026-09-05 · 状态：生效
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

1. 首次使用后，「显示主密钥」→ 复制 `AGE-SECRET-KEY-...` 存入密码管理器；
2. 另做至少一份物理隔离的离线备份（U 盘/纸质）；
3. 主密钥 + 主机同时丢失 = 全部秘密不可恢复，只能逐条重置（ADR-0040）。

主密钥文件本身也要随宿主导出/备份策略保护，但它**永不进入 git**（.gitignore 已排除；
`secrets/*.age` 密文快照例外，可入库）。

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

1. `.env` 或主机丢失：取任一导出包 + 主密钥，`extract` 解出全部秘密，重建 `.env` 与组件配置，
   重跑初始化按恢复式收敛（ADR-0039）。
2. 导出包可疑损坏：`verify` 不带密钥先验包完整性（payload 摘要），带密钥逐条验明文摘要。
3. 主密钥泄漏：生成新主密钥（删除 `secrets/master.key` 后任意操作触发重建），逐条轮换全部
   秘密值（新密文用新密钥），含 `critical` 标记的按轮换风险提示处置。

## 二期预告（未实现）

scope ACL（员工按授权范围在线取密）、接收者密钥对（提交即加密、秘密只在 CI 内解密）、
证书过期主动告警、分发包。设计见 ADR-0043/0044。
