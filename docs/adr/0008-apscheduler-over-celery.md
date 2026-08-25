# ADR-0008 调度器选 APScheduler 而非 Celery+Redis

> 日期：2026-08-21 · 状态：已接受
> 关联：how/manager-architecture.md §2.2；需求 FR-MGR-004；原则"最小依赖"
> （本篇为文档重构时对原 docs/02 §13.2 决策的追记）

## 背景

Manager 需要 cron 定时 + 手动 + webhook 触发任务，任务定义需持久化在 DB。并发量小（个位数并发 Run）。

## 决策

选 **APScheduler**（AsyncIO + SQLAlchemyJobStore），不引入 Celery + Redis。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| Celery + Redis | 并发量小，用不上分布式队列；多引入一个中间件多一份运维（违反最小依赖原则） |
| 系统 cron | 任务定义不入库、无法与 Run 生命周期联动 |

## 后果

- 正面：任务定义在 Postgres、支持 cron/interval、零新增中间件。
- 负面：单进程调度，Manager 多副本部署时需处理调度单例（当前单容器部署无此问题）。
- 同步：manager/（调度器实现）。
