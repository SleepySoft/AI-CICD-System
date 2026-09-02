# 构建与安装 sealed Chronicler

> 版本：v1.0 · 日期：2026-09-02 · 状态：生效
> 定位：在目标原生平台构建、验证并安装 sealed Chronicler；不负责打包组件或代码签名服务配置
> 关联需求：FR-MGR-029、FR-MGR-030；决策：../adr/0036-sealed-runtime-prompt-catalog.md

## 前置条件

- 在目标 OS/架构本机或同构 CI runner 构建；产物不能跨 OS 使用。
- 已安装 CPython 3.11，并按 `chronicler/requirements-build.txt` 创建独立干净虚拟环境。Python 3.14 + Nuitka 4.2 编译 FastAPI/Pydantic 后黑盒启动失败，当前构建器会提前拒绝。
- Windows 安装 Visual Studio 2022 C/C++ Build Tools；Linux 安装 GCC/Clang；macOS 安装 Xcode Command Line Tools。
- 发行版本使用 SemVer，例如 `1.0.0`。

## 构建

Windows PowerShell 5.1：

```powershell
py -3.11 -m venv build\chronicler\venv311
.\build\chronicler\venv311\Scripts\python.exe -m pip install -r chronicler\requirements-build.txt
.\scripts\build-chronicler.ps1 -Version 1.0.0 -Output dist
```

Linux/macOS：

```bash
python3.11 -m venv build/chronicler/venv311
build/chronicler/venv311/bin/python -m pip install -r chronicler/requirements-build.txt
bash scripts/build-chronicler.sh 1.0.0 dist
```

先验证资源组织和 Prompt 加密而不执行 C 编译时使用 `-BundleOnly`（PowerShell）或第三参数 `--bundle-only`（bash）。bundle-only 目录不可安装。

## 验证发行目录

1. 查看 `manifest.json`：`profile` 必须为 `sealed`，正式发行的 `source_dirty` 必须为 `false`，`components_included` 必须为 `false`，每个 Prompt 只有 name/version/content_hash 元数据。
2. 确认 `resources/prompts.bundle` 存在，发行目录无 Prompt YAML、Python 源码和 `_sealed_profile.py`。
3. 在不提供源码仓的临时目录复制 `.env.example` 为 `.env`，运行 `chronicler.exe serve`（Windows）或 `./chronicler serve`（Linux/macOS）。
4. 访问 `/api/health`，预期 `ok=true`；登录后 Prompt 页内置项只显示元数据，Run 的提示词视图只显示 name/version/hash。
5. 运行一次 stdin harness 和一次文件 harness；完成后 `data/private/chronicler/runs/<id>/` 不应保留 `prompt.md`。

构建报告位于 `build/chronicler/compilation-report-<platform>.xml`，依赖缺失时先查该文件。
构建器使用单 C 编译任务，优先保证 Windows/MSVC 与受限 CI 环境稳定性；首次构建耗时较长，后续由 Nuitka 编译缓存加速。

## 安装

Windows：

```powershell
.\scripts\install-chronicler.ps1 -ReleaseDir dist\chronicler-1.0.0-windows-x86_64 -InstallDir C:\Chronicler
```

Linux/macOS：

```bash
bash scripts/install-chronicler.sh dist/chronicler-1.0.0-linux-x86_64 /opt/chronicler
```

安装器保留已有 `.env`，首次安装从 `.env.example` 创建；随后必须编辑占位凭据。

## 外置组件

核心发行包不含组件。可在安装时从独立目录 provision：

```powershell
.\scripts\install-chronicler.ps1 -ReleaseDir <release> -InstallDir C:\Chronicler -ComponentsDir C:\ChroniclerComponents
```

```bash
bash scripts/install-chronicler.sh <release> /opt/chronicler /opt/chronicler-components
```

目标结构为 `<install-root>/components/<name>/plugin.yaml`。组件包含 Python hook 时，sealed 运行环境需提供独立解释器；必要时设置 `CHRONICLER_COMPONENT_PYTHON`。组件仍按 ADR-0027 独立发布和演进。

## 回滚

1. 停止新版本服务。
2. 保留安装根 `data/` 和 `.env`。
3. 将上一版本发行目录重新安装到新的安装目录，挂接原 `data/` 路径后启动。
4. 若 SQLite 已发生不向后兼容迁移，使用升级前备份恢复；当前 additive 迁移可直接由旧版本忽略新增列。

## 已知限制

- 内置 AES key 可阻止直接读取和普通复制，但不抵抗本机管理员的专业动态逆向。
- 第三方 harness 可能自行记录完整 Prompt；需按 harness 产品能力关闭遥测/历史或使用受控账号。
- Linux 发行应在支持范围内最老的目标发行版构建，避免 glibc 向后兼容问题。