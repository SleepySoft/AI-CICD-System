# 需求库说明

> 版本：v1.0 · 日期：2026-08-25 · 状态：生效
> 定位：本项目需求的唯一机器可读事实源；规则详见 `.agents/skills/docs-management/references/requirements-scheme.md`

## ID 前缀

| 前缀 | 层 | 文件 |
|------|----|------|
| `BR` | 业务需求 | `business.md` |
| `UR` | 干系人需求 | `stakeholder.md` |
| `FR-<MOD>` | 功能需求 | `functional/<模块>.md` |
| `NFR` | 非功能需求 | `non-functional.md` |

## 模块短码注册表（FR-<MOD>-NNN）

| 短码 | 模块 | 需求文件 | 设计文件 |
|------|------|---------|---------|
| `ENV` | 环境编排（compose/Caddy/门户/监控） | `functional/env.md` | `../what/environment.md`、`../how/deployment.md` |
| `CI` | CI/CD 流水线（Jenkins） | `functional/ci.md` | `../how/images-toolchain.md` |
| `IMG` | 工具链与运行时镜像 | `functional/images.md` | `../how/images-toolchain.md` |
| `KB` | 知识库（vault/Qdrant/Outline） | `functional/kb.md` | `../what/knowledge.md` |
| `REQ` | 需求管理工具链 | `functional/req.md` | `../what/req-mgmt.md` |
| `TASK` | 任务管理（OpenProject 工作包 + AI 回写） | `functional/task.md` | `../what/task-mgmt.md` |
| `MGR` | Manager 管理服务 | `functional/manager.md` | `../what/manager.md`、`../how/manager-architecture.md` |

新增模块短码：在本表注册后再使用，短码 3~4 位大写字母、全局唯一。

## 铁律

1. 需求文本只在本目录维护；其它文档只引用 ID。
2. ID 一次分配终身不变；废弃标 `状态: 废弃`，不删除不复用。
3. 每条 FR/NFR 必须登记进 `traceability.md`。
