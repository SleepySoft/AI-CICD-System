# ADR-0035 以有效输入快照驱动增量提示与自动任务

> 日期：2026-09-02 · 状态：已接受
> 关联：../what/manager.md §2.3.1；需求 FR-MGR-027、FR-MGR-028、UR-011

## 背景

Run 已记录主仓 `repo_head`，但用户无法直接看到本次相对上次分析增加了哪些提交；定时任务也会在没有变化时重复消耗 Agent。仅比较主仓 HEAD 又不能覆盖混合构建输入：例如脚本解析动态依赖后，声明版本不变而实际制品 revision 已变化。

不同包管理器的锁文件、远端 revision 与解析命令差异很大，当前阶段为 Conan 等系统逐一内置适配会扩大范围。管理员已经能够配置受信任的 harness 命令，因此可用同样的管理边界配置只读变更探针。

## 决策

1. 每个 Run 在 Agent 前冻结有效输入快照：主仓完整 Git revision + 可选 command probe 指纹，并计算规范化总指纹。
2. 基线为同一 task_id 最近一次 `success` Run；没有 task_id 的直接触发按工程 + task_type 查找。`skipped` 不替代成功基线。
3. Git 增量区分 initial、unchanged、changed、diverged；无法取得基线对象或 probe 执行失败为 unknown。
4. command probe 在工程仓根执行，stdout 去除首尾空白后计算 SHA-256；不保存 stdout。命令由 admin 配置，默认超时 60 秒。
5. 任务策略为 `always`（默认）、`repo-changed`、`inputs-changed`。策略只影响自动触发；无相关变化时创建 skipped Run。unknown 一律继续执行。
6. 手动触发先显示同一套增量预览，无增量时加重提示，但用户确认后仍运行。
7. 不内置 Conan/包管理器适配。用户可配置确定性的 command probe；不能可靠解析的混合项目保持 `always`。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 只比较主仓 Git HEAD | 无法感知动态依赖、外部制品或生成输入变化 |
| 每种依赖系统内置适配器 | 当前需求和测试样本不足，适配维护成本高 |
| 无变化时不留 Run | 无法区分调度器未工作与正确跳过，破坏审计链 |
| 探测失败按无变化跳过 | 网络、凭据或脚本故障会静默漏跑任务 |
| 手动触发也强制跳过 | 阻碍重跑、验证 Prompt 或恢复失败任务 |

## 后果

正面：历史可解释每次分析基于什么变化；自动任务减少无效调用；Git 与非 Git 输入使用统一指纹模型；混合项目可渐进配置。

负面：自动触发前增加同步和 probe 时间；command probe 必须由管理员保证确定性和只读性；跨平台命令由项目自行维护；Conan 等系统暂不提供开箱适配。

同步更新：../requirements/stakeholder.md、../requirements/functional/manager.md、../requirements/traceability.md、../what/manager.md、../how/manager-architecture.md、../README.md。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->