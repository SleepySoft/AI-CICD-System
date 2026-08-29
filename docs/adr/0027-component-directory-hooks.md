# ADR-0027 组件目录自包含与钩子契约（备份/部署下放组件层）

> 日期：2026-08-27 · 状态：已接受
> 关联：ADR-0024（组件即 SKILL）、ADR-0025（SKILL 存在即声明）、ADR-0026（数据二分）、ADR-0015（备份策略）、FR-MGR-022（组件生命周期）

## 背景

组件插件化（FR-MGR-022）后，组件信息散落于 tools.d/（注册）、skills/（能力，ADR-0024）、以及硬编码在 supervisor 里的部署/备份逻辑（compose service 名、pg_dump 等）。这暴露两个矛盾：

- **supervisor 不应包含任何组件相关知识**：它不知道会有哪些组件（ADR-0022 可选底座），但备份/部署逻辑却写死在 supervisor/脚本里（scripts/backup.sh 逐服务硬编码）。
- **备份/部署与组件强耦合**：pg_dump 属于 postgres 的知识，`npm install -g` 属于某 CLI 的知识——只有组件自己知道怎么备份/部署自己。

## 决策

1. **组件目录自包含**：一个组件一个目录，装下自己的一切：
   ```
   chronicler/components/<name>/
   ├── plugin.yaml        # 注册与生命周期（name/group/desc/url/container/visibility/
   │                      #  autostart/critical/driver/data 声明/compose_service）
   ├── SKILL.md           # 能力描述（可选；存在即注入，ADR-0025）
   └── hooks/
       ├── backup.py      # 备份/恢复（可选；缺省=文件 tar 兜底）
       └── deploy.py      # 部署（可选；缺省=docker compose up -d <compose_service>）
   ```
   用户侧目录 `data/chronicler/components/<name>/` 同构覆盖。supervisor 只做**目录扫描 + 契约调用**，不含任何组件特定信息。
2. **钩子契约**（CLI 约定，supervisor 唯一依赖）：
   - `backup.py backup --dest <dir>` / `restore --src <dir>` / `manifest`；退出码 0 成功；stdout 末行输出 JSON（covers/requires/skipped/大小）；未部署组件返回 `{"skipped": true}`。
   - `deploy.py up` / `down`（缺省回落 compose）；退出码语义同上。
3. **备份编排器**：发现所有钩子 → 收集 manifest → 按 `requires` 拓扑排序（如 gitea 依赖 postgres 先恢复）→ 逐个执行 → 汇总顶层 `manifest.json` → 打包 `data/backups/<timestamp>/`。恢复逆序。无钩子组件按默认文件策略兜底并标记"未声明备份能力"。
4. **一致性语义**：在线备份尽力而为（pg_dump 有事务一致性，文件型 rsync/tar 即可）；严格一致走维护窗口停组件，写进契约不强制。
5. **tools.d/ 与 components.yaml 废除**：注册信息并入 plugin.yaml（含 enabled/note/prompt 注入字段）；skills/ 目录约定改为组件目录内 SKILL.md。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 备份保持 supervisor 集中编排（现状 backup.sh） | supervisor 被迫携带组件知识；新增组件要改 supervisor——违背插件化 |
| 钩子用 bash 而非 python | 跨平台（Windows 宿主无 bash 保证）；supervisor 本身是 python，同语言降低契约摩擦 |
| 组件目录合并进 supervisor 包外单独仓库 | 内置组件随产品走是合理默认；用户自定义组件走 data/ 覆盖目录，两全 |
| 钩子用 HTTP 回调而非 CLI | 组件未运行时无法回调；CLI 无前置依赖 |

## 后果

- 正面：新增组件 = 一个目录（含部署/备份/能力自述），supervisor 零改动；备份/恢复粒度到组件且可组合；ADR-0015 的一键备份保留（编排器即其一键实现）。
- 负面：钩子质量依赖组件作者；契约演进需版本化（v1 先不版本，靠约定）。
- 待办：loader 重写（扫 components/）；编排器 + CLI（`python -m chronicler backup|restore`）；postgres/gitea 示范钩子；deploy.py 支持；scripts/backup.sh 改为薄壳；what/environment.md §2.5、FR-MGR-022、runbooks/backup-restore.md 同步。
- 同步：docs/README.md 索引登记本篇。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->
