# ADR-0017 Agent 生命周期：CLI 后装持久卷 + 登录态持久化 + 首次交互登录

> 日期：2026-08-26 · 状态：部分被 ADR-0021 推翻（决策 1"后装进容器持久卷"被推翻；登录态持久化与 endpoint 抽象仍有效）
> 关联：what/manager.md（agent_profile、Agent 终端）；需求 FR-MGR-002、NFR-002、NFR-008；ADR-0012、ADR-0016

## 背景

系统架构不是 agent 驱动，而是 **Manager 调用 agent + 预置 prompt 处理事务**；agent 经 ATR 维持长会话、保持上下文，由 ATR 提供 API 供 Manager 使用。要支持 kimi / claude / codex / pi 等多家 CLI，决策时刻已知的约束：

- 各家登录方式不一且**不稳定**：有的网页 OAuth（Claude Code）、有的 API key、有的要 cc-switch 类转发改 base_url——"不是定的"，无法内置一套固定流程。
- 装进镜像：agent 更新频繁导致镜像反复重建、体积膨胀；且登录态/配置本来就要落持久层，预装只省首次几分钟。
- 装宿主直接跑：宿主污染、Windows/WSL 环境分裂、密钥扩散面大、失去容器隔离。

## 决策

1. **Agent CLI 后装到持久卷**：镜像只提供运行底座（node/python/tmux 等）；各家 CLI 首次使用时按脚本安装到 `${DATA_ROOT:-./data}/agents/<name>/`（安装前缀与 HOME 均指向该目录），安装脚本锁定版本，版本记入 `agent_profile`。
2. **登录态持久化 + 首次交互登录**：网页/OAuth 类登录由人经 Manager 的 Agent 终端（ATR 会话，FR-MGR-002）一次性完成，凭据随配置目录落持久卷，后续 Manager 非交互复用；API key 类走 NFR-002 密钥管理（`api_key_ref`）。
3. **转发层抽象为 endpoint 配置**：Manager 只认 `base_url` + key（agent_profile 已有字段）；cc-switch 类转发如需要，作为独立可选 compose 服务另行引入，不耦合进 agent 安装。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 全部预装进镜像 | 见背景：重建频繁、体积膨胀，登录态仍需落卷 |
| 装宿主直接跑 | 见背景：污染宿主、环境分裂、密钥扩散 |
| 每次任务全新会话现登录 | OAuth 类无法非交互登录；且丢掉 ATR 长会话保持上下文的核心价值 |
| Manager 内置适配各家登录流程 | 登录方式不稳定，内置 = 持续追债；交互登录 + 持久化一次解决 |

## 后果

- 正面：镜像小且稳定（NFR-005 底座可复现）；登录一次长期有效；新增一家 agent = 一段安装脚本 + 一条 agent_profile，不动镜像；agent 数据落数据根，随 backup.sh 一并覆盖（ADR-0015）。
- 负面：首次使用有安装耗时；agent 版本漂移靠安装脚本锁版本约束；OAuth token 过期需人工重新登录（OAuth 的本质限制，任何方案都存在）。
- 同步：what/manager.md agent_profile 契约补充（安装与登录约定）；安装脚本与 agent-runner 镜像随 M2 落地。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
