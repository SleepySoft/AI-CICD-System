# Runbook: 清理派生资源并重新分析

> 版本：v1.0 · 日期：2026-09-28 · 状态：生效
> 适用：管理员清理工程 Shadow、工作区克隆和残留目录；不清理源仓远端或 Outline 数据。
> 关联需求：FR-MGR-032；外部契约见 [Chronicler 规格](../what/manager.md#危险资源清理)。

## 目的与风险

清理页用于删除可以从源仓重新分析的资源。**删除不可由 Chronicler 回滚**；本地 Shadow 的未推送提交在删除后可能永久丢失。先检查页面显示的 HEAD、最近 Run 与推送状态。需要保留历史时，先自行备份对应目录或远端仓库。

## 操作步骤

1. 用 admin 账号直接打开 `http://app.localhost/maintenance/cleanup`（若直连 supervisor，使用 `http://127.0.0.1:8600/maintenance/cleanup`）。此页不在日常导航中。
2. 点击「重新检查资源」，核对工程名、本地 Shadow HEAD、最近 Run 和推送状态。存在排队或运行中任务时先等待任务结束。
3. 若要从头重新分析，勾选「本地 Shadow」与「受管 Gitea Shadow 远端仓库」。仅删本地 Shadow 时，下次运行会从仍存在的远端拉回旧文档。可按需再选源仓工作区克隆；此操作只删本地副本。
4. 点击「核对并确认」，输入页面给出的完整确认文字，再点击「永久删除」。若清单变化，重新预览并确认。残留克隆需逐个单独确认。
5. 返回工程页同步源仓工作区，重新触发项目分析或认知维护任务；查看新 Run 的摘要、Shadow 初始化与推送状态。

## 验证

在 PowerShell 中执行以下只读检查，预期清理目标已不存在或远端配置为空；新任务成功后会重新建立 Shadow。

```powershell
chronicler\.venv-win\Scripts\python.exe -m chronicler check
```

`check` 会报告尚未重建的工作区差异；任务重建完成后再次执行并确认该工程无 Shadow 版本差异。审计页面可按 `maintenance.cleanup` 查询逐项结果。远端删除失败时本地 Shadow 会保留；页面会显示失败，修复 Gitea 可达性或配置后重试。

## 恢复

仅在删除前做过备份，或远端仍保留副本时，才能恢复被删内容。源仓工作区克隆可从工程页重新同步；若同时删除了本地和远端 Shadow，只能通过重新分析生成新认知资产。Outline 页面和附件仍由 Outline 的数据库与私有目录管理，本页不处理。
