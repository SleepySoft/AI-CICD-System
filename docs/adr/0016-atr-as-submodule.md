# ADR-0016 terminal-runtime-skill 以 git submodule 引入（替代 vendored 拷贝）

> 日期：2026-08-26 · 状态：已接受
> 关联：images/terminal-runtime/Dockerfile；上游仓库 https://github.com/SleepySoft/terminal-runtime-skill.git

## 背景

ATR（terminal-runtime-skill）是独立上游项目。M1 时为求快将其代码 vendored 进 `third_party/`（scripts/git-prepare.sh 剥掉内嵌 .git 后整体提交）。后果已经显现：上游更新无法跟踪、本地修改无法回流、副本随时间漂移。

## 决策

`third_party/terminal-runtime-skill` 改为 **git submodule**，锁定上游 commit；`images/terminal-runtime/Dockerfile` 的 COPY 路径不变，构建不受影响。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持 vendored 拷贝 | 双写漂移；上游修复需手工同步，本地改进烂在副本里 |
| git subtree | 可内联修改并推回上游，但合并历史复杂；本项目只需只读跟踪上游 + 偶尔提 PR，submodule 够用且边界更清晰 |
| pip/npm 包依赖 | 上游未发包；且 SKILL.md 等资料需要随仓库可查 |

## 后果

- 正面：上游可跟踪可更新（`git submodule update --remote`）；改进可回流上游；版本锁定明确。
- 负面：克隆需 `git clone --recurse-submodules`（或事后 `git submodule update --init`）；GitHub 网络不通时子模块拉取需代理。
- 待办（网络可用时执行，当前本机 GitHub 直连不通）：`git rm -r third_party/terminal-runtime-skill` → clone 上游到原路径 → `git submodule add` 注册 → 比对内容与 vendored 副本差异。
- 同步：删除 scripts/git-prepare.sh（其存在意义被 submodule 取代）；部署文档补 `--recurse-submodules` 说明。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
