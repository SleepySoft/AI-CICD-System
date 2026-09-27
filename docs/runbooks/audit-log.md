# 查询操作与启动审计

> 版本：v1.0 · 日期：2026-09-27 · 状态：生效
> 定位：追查 Chronicler 操作、配置与秘密变更、运行时初始化；不替代组件业务日志。
> 关联需求：FR-INIT-018

## 适用场景

配置或密钥变化后服务异常，需要确认操作者、变化对象、秘密来源及初始化结果。
补丁加载后产生新记录；无法从新机制补造以前缺失的历史。

## 网页查询

1. 更新后重启 Chronicler（PyCharm 调试时停止并重新运行原启动配置）。
2. 用管理员账号登录，打开「审计日志」。
3. 按操作者、动作、目标或结果查询；目标可填秘密名称。
4. 在详情中找到 `correlation_id`，填入「关联编号」后查询同一次操作的完整链路。
5. 点击「加载更早记录」继续查看；刷新从最新记录开始。

普通用户被拒绝访问。原「秘密库 → 存取审计」保留，提供最近 500 条秘密库记录。

## 常见动作

| 查询动作 | 查看内容 |
|---|---|
| `runtime.` | 每次应用启动、迁移、会话密钥加载、任务调度和组件自启 |
| `vault.master_key.` | OS 钥匙串读取、文件回落、主密钥验证及生成/保存 |
| `vault.secret.read` | 秘密库条目解密结果，缺条目、锁定和解密失败 |
| `vault.mutation.` | 秘密新增、替换、删除、元数据修改及失败 |
| `vault.replacement_rejected` | 受保护数据加密密钥替换被拒绝 |
| `config.field.update` | `.env` 配置逐项保存；只记录字段名与存在/变化状态 |
| `setup.` | 向导输入暂存、运行步骤、组件和运行结果 |
| `component.` | 部署、确保运行、能力脚本执行 |
| `http.mutation` | HTTP 写操作的操作者、方法、路径及响应状态；不记录请求正文或 URL 查询串 |

### 秘密来源与结果

`source` 区分 `os-keyring`、`master-key-file`、`vault`、`env-file`、`process-env`、
`default`、`setup-input`、`encrypted-export`。`consumer`（如有）标记调用来源。
主密钥读取失败后文件回落成功是两条记录，不能只看最初的失败便判定启动失败。

`result` 包含 `started`、`success`、`failed`、`blocked`、`missing`、`skipped`、`unchanged`。
异常只记录类型，不记录可能含秘密的异常文本、命令参数、子进程输出或连接串。
`before_revision` / `after_revision` 是密文 SHA-256，用于判断存储版本变化，不能拿来比较容器明文。
元数据变更记录字段名，不记录自由文本的前后值。

## 验证

重启后查询 `runtime.initialize`，应看到同一关联编号的开始和完成记录；失败启动有失败记录。
查询 `vault.master_key.read` 和 `vault.secret.read`，可看到实际读取来源和结果。
使用真实生产秘密进行检查时，只看名称和状态，勿复制解密值到工单。

PowerShell，仓库根执行自动化验证：

```powershell
chronicler/.venv-win/Scripts/python.exe -m unittest chronicler.tests.test_vault chronicler.tests.test_initialization chronicler.tests.test_secret_deployment chronicler.tests.test_component_exec -q
```

预期输出包含 `OK`；覆盖权限拒绝、游标分页、逐项变更、读取失败、钥匙串回落和初始化失败脱敏。

## 记录位置与边界

记录保存在 `data/private/chronicler/chronicler.db` 的 `audit_log` 表（`CHRONICLER_DATA` 可覆盖目录）。
向导同时保留原 `setup_runs` / `setup_steps` / `setup_events`，新增的运行发起人跨重试与重启保留。
当前不自动清除审计，也不提供删除 API；数据库须纳入宿主备份并限制写权限。

应用数据库尚未可用时，初始化失败只能由进程启动日志报告。直接改文件、数据库或在程序外
执行 Docker 命令不会产生 Chronicler 操作审计；本机制不提供防管理员篡改的外部日志存证。
历史字符串详情可查看，但没有结果或关联编号的旧记录无法按这两个字段筛选。

本手册查询操作无业务副作用，不需要回滚。若回退应用版本，保留数据库和审计记录；不要删除
数据目录，也不要为恢复旧代码更换数据加密密钥。
