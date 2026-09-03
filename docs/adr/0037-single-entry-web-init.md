# ADR-0037 初始化收归单一入口：Web 初始化界面，启动脚本回收

> 日期：2026-09-03 · 状态：已接受
> 关联：[ADR-0029 supervisor 唯一入口与 .env 前置校验](0029-supervisor-single-entry-env-prereq.md)；[ADR-0027 组件目录自包含与钩子契约](0027-component-directory-hooks.md)

## 背景

- 从零搭建当前依赖 `scripts/up.sh` → `wire-sso.sh` / `wire-chronicler.sh` / `verify*.sh` 等一组
  shell 脚本，与 ADR-0029 确立的"`python -m chronicler` 唯一入口"原则相悖，且 shell 脚本在
  Windows Git Bash 下有实测坑（MSYS 把容器内路径 `/opt/...` 转成 `C:/Program Files/Git/...`，
  kcadm 直接不可用）。
- 2026-09-03 实测事故：统一登录报 Keycloak "Client not found"，根因是 `aisystem` realm 中从未
  成功创建 `chronicler` OIDC 客户端（`wire-chronicler.sh` 未在当前数据上跑过）；同期还发现
  `.env` 的 `KEYCLOAK_ADMIN_PASSWORD` 与容器初始化密码漂移（kcadm/kc_admin.py 均失效）。
  脚本化接线"跑没跑过、跑没跑成"不可见，是事故温床。
- 用户当日已指示完全清除旧环境（12 个 aisystem 容器、网络、匿名卷、`data/` 全部组件数据），
  准备测试从零搭建，初始化路径必须先定型。
- supervisor 已具备可复用能力：`tools.py` 的 compose 拉起/共享网络/异步部署、`kc_admin.py`
  的 httpx Admin REST 回源模式、`Cfg.require_env` 的 .env 校验。

## 决策

初始化全流程收归 Chronicler 单一入口，以 **Web 初始化界面** 提供（含本地 admin 创建），
不再依赖任何 shell/ps1 启动脚本；被取代的脚本移入 `recycled/`。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 新增 `python -m chronicler init` CLI 子命令 | 用户明确选择网页形态；从零搭建的引导对操作者更友好，进度/日志可视化 |
| serve 启动时全自动初始化 | 首次启动阻塞过久，失败语义不清；初始化是显式一次性动作，不应混入日常启动 |
| 维持 shell 脚本链路 | 双入口违背 ADR-0029；跨平台坑（MSYS 路径转换、编码）已实测踩中 |

## 后果

- 正面：初始化状态可见、幂等可重入；接线逻辑进入 Python（httpx Admin REST + docker SDK），
  消除 kcadm/MSYS 依赖；admin 创建与组件拉起、SSO 接线在同一引导流内完成，杜绝"漏跑脚本"事故。
- 负面：需在 supervisor 内新写"等容器 healthy"、docker exec（gitea `-u git`）、
  Keycloak clients/client-scopes CRUD 等封装；Web 初始化界面本身是未认证前置页面，需限定
  仅在"未初始化"状态开放。
- 待定项：回收脚本的最终范围（候选 `up.sh`、`wire-sso.sh`、`wire-chronicler.sh`、`verify.sh`、
  `verify-chronicler.sh`、`backup.sh`/`restore.sh` 薄壳；`fix-hosts.*`、`dev-sync.sh`、
  `check-kc.sh`、`wire-jenkins-job.sh` 另议）。
- 实施时须同步更新：AGENTS.md「部署/验证」章节、`docs/runbooks/deploy.md`、docs/README.md 索引。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
