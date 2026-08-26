---
name: openproject
description: Agent 操作 OpenProject（任务/需求管理系统）的约定与 API 用法。当需要读取任务清单、领取任务、回写状态与评论、从文本批量创建任务，或查询工作包上下游关系时使用。适用于交互式 Agent 会话；Manager 自动化任务的 API 封装代码也以此文件约定为准。
---

# OpenProject 操作规范（Agent 用）

> 服务由 compose `requirements` profile 提供，默认地址 `http://req.localhost`（容器间可用 `http://openproject:8080`）。
> 决策背景见 `docs/adr/0011-openproject-task-management.md`；使用模式是"人提任务、AI 执行并标记"。

## 认证

- API v3，认证方式为 HTTP Basic：**用户名固定为 `apikey`，密码为个人 API token**。
- token 由人在 OpenProject「我的账户 → 访问令牌（Access tokens）」生成，运行时从环境变量
  `OPENPROJECT_API_KEY` 读取；**token 绝不入库、绝不写进任何提交**。
- 交互会话中若无 token，向人要，不要自己注册账号。

## curl 规范

- 本环境已知坑：WSL 中代理会拦截 localhost/内网请求，一律 `curl --noproxy '*'`。
- 响应是 HAL+JSON；集合端点分页参数 `offset`/`pageSize`，条目在 `_embedded.elements`。

## 核心操作速查

```bash
OP="${OPENPROJECT_URL:-http://req.localhost}"
AUTH="apikey:${OPENPROJECT_API_KEY}"

# 项目清单
curl --noproxy '*' -sS -u "$AUTH" "$OP/api/v3/projects"

# 打开状态的工作包（filters 需 URL 编码；o = open）
curl --noproxy '*' -sS -u "$AUTH" -G "$OP/api/v3/work_packages" \
  --data-urlencode 'filters=[{"status":{"operator":"o","values":[]}}]'

# 单个工作包（标题/描述/状态/指派/关系链接都在里面）
curl --noproxy '*' -sS -u "$AUTH" "$OP/api/v3/work_packages/123"

# 更新状态或字段：PATCH 必须带当前 lockVersion（乐观锁，先从 GET 响应取）
curl --noproxy '*' -sS -u "$AUTH" -X PATCH "$OP/api/v3/work_packages/123" \
  -H 'Content-Type: application/json' \
  -d '{"lockVersion": 5, "_links": {"status": {"href": "/api/v3/statuses/7"}}}'

# 评论（执行进展、结果摘要、阻塞原因都落评论）
curl --noproxy '*' -sS -u "$AUTH" -X POST "$OP/api/v3/work_packages/123/activities" \
  -H 'Content-Type: application/json' \
  -d '{"comment": {"format": "markdown", "raw": "执行完成，摘要见…"}}'

# 从文本创建任务：在指定项目下建工作包
curl --noproxy '*' -sS -u "$AUTH" -X POST "$OP/api/v3/projects/my-project/work_packages" \
  -H 'Content-Type: application/json' \
  -d '{"subject": "任务标题", "description": {"format": "markdown", "raw": "正文"},
       "_links": {"type": {"href": "/api/v3/types/1"}}}'

# 上下游关系：顶层 relations 端点按 from/to 过滤；创建关系用
# POST /api/v3/work_packages/{id}/relations，body 指定 to 链接与 relationType（follows/precedes/blocks…）
curl --noproxy '*' -sS -u "$AUTH" -G "$OP/api/v3/relations" \
  --data-urlencode 'filters=[{"from":{"operator":"=","values":["123"]}}]'
```

> 状态/类型的 href ID 因实例而异：先 `GET /api/v3/statuses`、`GET /api/v3/types` 拿到本实例的映射，
> 不要硬编码。API 细节以实例实际版本（OpenProject 15）为准，出入时以 `GET /api/v3` 根文档核对。

## 状态流转约定（人提、AI 执行、AI 标记）

- **人**：建任务、定优先级、验收关闭（`closed` 只能由人设置）。
- **AI**：领取时置 `in progress` 并评论认领；完成后置约定完成态（如 `done`/`to be reviewed`）并评论结果摘要与产出位置；阻塞时保持状态并评论阻塞原因，不得擅自关闭。
- AI 不改动非自己认领的任务；不改 `subject` 与需求关联，除非任务明确授权。

## 提交关联约定

提交信息带 `OP#<工作包ID>`（如 `fix: 修正分页 OP#123`），供 Gitea 提交与工作包互相定位；
AI 产出提交时必须遵守，回溯时由 Manager/人按此约定反查。

## 边界与配套

- 审计/文本快照：人工运行 `scripts/export-openproject.sh` 导出 JSON+Markdown 快照（手工入口，见 ADR-0014）；AI 需要离线文本视图时提醒人跑一次导出。
- 附件、大文件不走 API 文本层；需要时评论中给链接。
- OpenProject 的 DB 不是事实源：需求条目的事实源在 Git（docs/requirements 或 Sphinx-Needs），任务运行态以 OpenProject 为准、快照入 Git 审计。
