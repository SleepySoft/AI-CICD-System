# Runbook: 备份与恢复

> 版本：v1.1 · 日期：2026-08-29 · 状态：生效
> 适用：Windows / WSL / Linux（组件化编排，跨平台）；Windows 下直接跑 python 命令
> 关联：chronicler/app/backup.py（编排器）、chronicler/components/\<name\>/hooks/backup.py（组件钩子）；决策 ../adr/0015-backup-strategy.md、../adr/0027-component-directory-hooks.md；数据布局 ../what/environment.md §2.5

## 目的

一键产出全量备份（`data/backups/<时间戳>/`），或从备份恢复整个环境。**组件化形态（ADR-0027）**：每个组件自己的 `hooks/backup.py` 负责备份自己，supervisor 只做发现、拓扑排序与汇总；无钩子的组件按默认文件策略兜底。Git 管理的数据层（docs/、knowledge/vault/）备份 = git 远端本身，不在本手册范围。

## 备份包结构

```
data/backups/<时间戳>/
├── manifest.json            # 顶层清单：每组件的结果（covers/files/skipped/error）
├── postgres/pg_dumpall.sql  # 组件钩子产出（postgres 全库，事务一致）
├── gitea/gitea-data.tar.gz  # 组件钩子产出（数据目录）
└── <无钩子组件>/*.tar.gz     # 兜底策略产出（标记 declared=false）
```

## 步骤

1. **在线备份**（默认，不影响服务）：
   ```bash
   bash scripts/backup.sh                      # 薄壳
   # 或等价直调：
   python -m chronicler backup                 # 输出到 data/backups/<时间戳>/
   python -m chronicler backup /path/to/dir    # 指定输出位置
   ```
2. **恢复**（覆盖现有数据；建议先跑一次备份留底）：
   ```bash
   python -m chronicler restore data/backups/<时间戳>
   ```
   恢复按依赖逆序（manifest 中 `requires`，如 gitea 在 postgres 之后）；备份包里有但当前未注册的组件会跳过并警告。
3. **组件级备份能力扩展**：给组件目录加 `hooks/backup.py`（契约：`backup --dest` / `restore --src` / `manifest`，stdout 末行 JSON），下次备份自动纳入，不用改 supervisor。

## 验证

```bash
python -m chronicler backup            # 跑完后检查：
cat data/backups/<时间戳>/manifest.json # 每组件 covers/files 非空且无 error
```

预期：manifest.json 中组件结果与备份包文件一一对应；`skipped:true` 仅应出现在未部署组件上。

## 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| 组件标记 declared=false | 未写 hooks/backup.py | 数据走默认 tar 兜底；要精细控制（如 dump）就补钩子 |
| postgres 钩子 skipped | 容器未运行 | 先在首页启动 postgres 再备份 |
| 恢复后服务异常 | 恢复时服务在写数据 | 恢复属维护操作，先停相关组件再 restore，完成后重启 |

## 回滚

- 备份只读不写数据目录，无回滚概念。
- 恢复会**覆盖** `data/`：执行前先 `python -m chronicler backup` 留底；恢复中途失败时，用留底备份再执行一次恢复即可。
