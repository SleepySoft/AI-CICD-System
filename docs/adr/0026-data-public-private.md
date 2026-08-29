# ADR-0026 数据目录 public/private 二分（扩展 ADR-0012）

> 日期：2026-08-27 · 状态：已接受
> 关联：what/environment.md（数据布局）；需求 NFR-008、NFR-009；ADR-0012（数据落宿主，本篇扩展）、ADR-0020（supervisor 宿主侧）、ADR-0024/0025（组件即 SKILL）

## 背景

ADR-0012 定了"服务数据显式 bind mount 到 `data/<服务>`"，等价于每服务私有目录。随着 supervisor 宿主化与组件按需部署（ADR-0020/0022），组件间需要文件交换的场景出现（报告、文档、导入导出、agent 产出），而数据库类组件的数据文件绝不应被其它容器看到。决策时刻已知的约束：

- 两类数据的访问媒介不同：API 型组件（postgres/redis/qdrant）数据文件私有；文件型产物（报告/文档/经验库）天生要被多方读。
- public/private 只解决**组件间**的访问边界；用户级权限是各系统自己的事（NFR-002、Keycloak），不在本决策范围。
- bind mount 同宿主无硬隔离，private 不是安全边界。

## 决策

1. **数据根二分**：
   ```
   data/
   ├── public/            # 交换区：统一挂载到所有容器 /public；宿主可直接读写
   │   └── <组件名>/      # 谁创建谁拥有；读别人随意、写别人禁止（约定，agent 侧经 SKILL 声明约束）
   └── private/<组件名>/  # 仅挂载到声明需要它的组件
   ```
2. **分类判定规则**：经 API 提供服务的 → private；以文件为交换媒介的 → public。默认 private。
3. **组件声明**：tools.d/ 插件加 `data:` 字段（`private: true/false`、`public_write: <子目录>`）；compose 统一挂载 `./data/public:/public` 进所有容器，`./data/private/<name>` 按声明进对应组件（替代现散写的 `./data/<服务>` 挂载，迁移时逐服务改）。
4. **机密永不落 data**：private 只是组织契约不是安全边界；密钥/口令永远走 `.env`/secret。
5. **supervisor 豁免**：Chronicler 在宿主直接读写，不受挂载约束；它是 public 的生产者（reports/）与管理员。
6. supervisor 自身产物落位调整：报告等文本产物迁往 `data/public/` 下，`chronicler.db`（SQLite）留 private 侧（`data/private/chronicler/` 或维持 data/chronicler，迁移时定）。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 维持每服务私有目录（ADR-0012 现状） | 无组件间文件交换通道；报告/资产库等多方共读的产物无处安放 |
| 全部数据 public | 数据库文件暴露给所有容器，误删/误读风险大 |
| 组件间经 API 交换文件，不要 public 区 | 强迫每个组件实现上传/下载 API；文本产物的天然形态就是文件 |
| private 做权限隔离（uid/acl） | bind mount 同宿主做不到真隔离，假装安全比承认契约更危险 |

## 后果

- 正面：组件间文件交换有标准通道；组件数据边界在插件文件里显式声明、可审查；与"组件即插件"（FR-MGR-022）同构。
- 负面：public 写入纪律靠约定与 SKILL 约束，无强制；存量服务挂载路径迁移需一次性改 compose（PG/Gitea 等数据目录搬迁要小心）。
- 待办：compose 挂载改造；tools.d/ 插件补 `data:` 声明；supervisor 产物路径迁移；what/environment.md 数据布局节更新。
- 同步：docs/README.md 索引登记本篇。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
