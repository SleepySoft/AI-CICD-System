# ADR-0036 构建时固化 sealed Profile 与结构化 Prompt Catalog

> 日期：2026-09-02 · 状态：已接受
> 关联：../what/manager.md §2.3.3；需求 BR-009、FR-MGR-029、FR-MGR-030

## 背景

源码开发需要完整 Prompt 可见性和热编辑，而保护交付要求 Chronicler 流程代码与内置 Prompt 不以可直接读取的形式出现。原实现直接扫描 Markdown 文件，并把渲染后 Prompt 同时写入 SQLite 与 Run 文件；仅在构建时加密源文件不能覆盖这些泄露路径。

组件是可选、可替换的外置底座资产（ADR-0027），将组件 hook 编译进 Chronicler 会反转所有权并增加每次新增组件都重建核心的耦合。因此本决策只覆盖 Chronicler 核心和内置 Prompt，不把组件代码并入二进制。

## 决策

1. Prompt 改为结构化定义，稳定身份为 name + SemVer version；schema_version、变量契约、输出种类和 content_hash 均由统一 Catalog 校验。
2. RuntimeProfile 在构建时固化为 source 或 sealed。source 加载 YAML 并披露正文；sealed 只能加载 AES-256-GCM bundle，不接受运行时降级开关。
3. sealed 内置 Prompt 的 API、页面和 Run 只披露 name/version/hash/变量元数据；用户覆盖存 DATA/prompts，仍可查看编辑。
4. sealed 执行优先 stdin；必须使用文件时只创建权限受限临时文件，执行结束后删除。第三方 harness 自身日志不在 Chronicler 的保密保证内，需部署者按产品策略配置。
5. 使用 CPython 3.11 + Nuitka standalone 在 Windows、Linux、macOS 对应原生 runner 构建，不跨平台复用二进制。发行包含编译核心、公开 static/config、加密 bundle、manifest 和安装脚本；升级构建 Python 前必须完成同等黑盒验证。
6. 组件不进入核心发行包。安装器只创建 `<install-root>/components/`，组件由单独分发/部署流程放入；sealed Python hook 使用外部 `CHRONICLER_COMPONENT_PYTHON`。
7. AES key 编译进 sealed 二进制，目标是防止直接读取和普通复制，不承诺抵抗本机管理员或专业动态逆向；更高等级保护需后续引入实例密钥或远程 Prompt 服务。

## 备选方案

| 方案 | 否决原因 |
|------|---------|
| 运行时环境变量切换 source/sealed | 用户可自行降级，不能形成安全边界 |
| Prompt 继续为 Markdown，仅构建时加密 | 缺少稳定版本、变量契约，且无法统一显示/覆盖/留痕 |
| 密钥放 `.env` | 客户必须持有密钥，直接解密 bundle，失去隐藏意义 |
| 所有组件和 hook 编译进 Chronicler | 组件所有权错位，新增组件必须重建核心 |
| Nuitka onefile | 长期服务每次解压、资源定位和杀毒误报成本高；standalone 更适合安装与诊断 |
| 承诺绝对防逆向 | 离线程序必须在本机解密并向 harness 提交 Prompt，技术上无法成立 |

## 后果

正面：source 开发体验不降级；sealed 的源码、Prompt 源文件、管理 API 和 Run 留痕边界一致；Prompt 具备稳定 name/version；组件继续独立演进；构建产物可按平台验证和签名。

负面：增加 cryptography/Nuitka 构建依赖；每个平台需要原生构建与黑盒测试；内置 key 只能提高逆向成本；用户自定义 Prompt 在 sealed 中不受隐藏保护；外置 Python 组件 hook 需要目标机有独立解释器。

同步更新：../requirements/business.md、../requirements/functional/manager.md、../requirements/traceability.md、../what/manager.md、../how/manager-architecture.md、../README.md。

<!-- 规则：ADR 只增不改。推翻旧决策时新建一篇并在旧篇状态字段标注"已被 ADR-MMMM 推翻"。 -->