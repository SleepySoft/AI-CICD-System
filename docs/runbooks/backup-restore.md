# Runbook: 备份与恢复

> 版本：v1.0 · 日期：2026-08-26 · 状态：生效
> 适用：WSL2 / Linux，compose 栈已部署；Windows 下在 WSL 中执行
> 关联：scripts/backup.sh、scripts/restore.sh；决策 ../adr/0015-backup-strategy.md；数据布局 ../what/environment.md §2.5

## 目的

一键产出全量备份（`backups/<时间戳>/`），或从备份恢复整个环境。Git 管理的数据层（docs/、knowledge/vault/）备份 = git 远端本身，不在本手册范围。

## 覆盖范围（全子系统）

| 子系统 | 数据位置 | 备份机制 |
|--------|---------|---------|
| Gitea（git 仓库 + 元数据） | `data/gitea` + PG `gitea` 库 | tar + pg_dumpall；仓库另有任一 git 克隆兜底 |
| Jenkins | `data/jenkins` | tar |
| Keycloak | PG `keycloak` 库 | pg_dumpall |
| Manager | PG `manager` 库（M2 起） | pg_dumpall |
| OpenProject | `data/openproject`（附件）+ PG `openproject` 库 | tar + pg_dumpall；文本快照另有 export-openproject.sh |
| Outline | `data/outline`（附件）+ PG `outline` 库 | tar + pg_dumpall |
| Qdrant | `data/qdrant` | tar（本质是可由 vault 重建的索引层） |
| Redis | `data/redis`（AOF） | tar（缓存性质，丢失影响小） |
| Ollama | `data/ollama`（模型权重） | tar（体积大且可重新拉取，可按需手工排除） |
| Uptime Kuma | `data/uptime-kuma` | tar |
| docs / knowledge vault / 配置 | Git 仓库 | git 远端即备份 |

每次备份的 `manifest.txt` 逐子系统列出本次实际覆盖方式，出现 `!! 未打包` 即异常。

## 步骤

1. 在线备份（默认，不影响服务） — 生成 `backups/<时间戳>/`，含 `postgres.sql` + 各服务 tar 包 + manifest
   ```bash
   bash scripts/backup.sh
   ```
2. 离线备份（强一致，用于大版本升级前） — 短暂停服，整体打包后自动拉起
   ```bash
   bash scripts/backup.sh --stop
   ```
3. 恢复（离线，覆盖现有数据，脚本会二次确认） — 全栈恢复并拉起
   ```bash
   bash scripts/restore.sh backups/<时间戳>
   ```

## 验证

```bash
bash scripts/verify.sh && bash scripts/verify-manager.sh
```

预期输出：验证脚本全绿；`backups/<时间戳>/manifest.txt` 中清单与实际文件一致。

## 回滚

- 备份只读不写数据目录，无回滚概念。
- 恢复会**覆盖** `data/`：执行前可先跑一次 `bash scripts/backup.sh` 留底；恢复中途失败时，用留底备份再执行一次恢复即可。
