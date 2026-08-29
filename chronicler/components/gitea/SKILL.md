---
name: gitea
description: Git 托管 API——查询仓库/提交/分支/issue。当任务需要代码历史、提交详情或创建 issue 时使用；不要用它执行 CI 构建（那是 Jenkins）。
---

# Gitea（代码托管）

## 能干什么

- 查询仓库列表、分支、提交历史与 diff：`GET {base}/api/v1/repos/{owner}/{repo}/commits`、`/compare/{base}...{head}`
- 查询/创建 issue 与 PR：`{base}/api/v1/repos/{owner}/{repo}/issues`
- 读取仓库文件内容：`GET {base}/api/v1/repos/{owner}/{repo}/contents/{path}`

## 不能干什么

- 不能触发/控制 CI 流水线（那是 Jenkins 的职责）
- 不做语义检索（那是 Qdrant）

## 怎么访问

- base URL：`http://git.localhost`（宿主/容器外）或 `http://gitea:3000`（容器内）
- 认证：API token 由任务环境经 `GITEA_TOKEN` 注入（若未注入则只读公开仓库）；**绝不把 token 写进产物**

## 何时选我而非别人

- 代码在 Gitea 托管时用我；工程 git_url 指向 GitHub 等外部远端时直接用 `git` 命令或对应平台 API，不必走我。
