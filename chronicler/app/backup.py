"""备份编排器（ADR-0027）：发现组件钩子 → manifest → 拓扑排序 → 执行 → 打包

supervisor 不含任何组件知识：每个组件的 hooks/backup.py 自包含备份逻辑；
无钩子的组件按默认策略兜底（tar 其 data 目录）并标记 declared=false。
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from .config import PKG_ROOT, Cfg
from .tools import load_tools

REPO_ROOT = PKG_ROOT.parent
BACKUPS_DIR = REPO_ROOT / "data" / "backups"
DATA_ROOT = REPO_ROOT / "data"


def _hook_path(tool: dict) -> Path | None:
    d = tool.get("_dir")
    if not d:
        return None
    p = Path(d) / "hooks" / "backup.py"
    return p if p.is_file() else None


def _run_hook(hook: Path, cmd: str, path: Path) -> dict:
    """调用组件钩子，返回其 stdout 末行的 JSON（契约见 ADR-0027）"""
    args = [sys.executable, str(hook), cmd]
    if cmd == "backup":
        args += ["--dest", str(path)]
    elif cmd == "restore":
        args += ["--src", str(path)]
    r = subprocess.run(args, capture_output=True, encoding="utf-8", errors="replace",
                       timeout=1800, cwd=str(PKG_ROOT.parent))
    last_line = (r.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError:
        result = {"raw_output": r.stdout[-500:]}
    result["exit_code"] = r.returncode
    if r.returncode != 0:
        result["error"] = r.stderr.strip()[-300:]
    return result


def _tar_skip_links(ti: tarfile.TarInfo):
    """跳过符号链接（WSL 容器里创建的链接在 Windows 宿主上打不开）"""
    return None if (ti.issym() or ti.islnk()) else ti


def _default_backup(tool: dict, dest: Path) -> dict:
    """兜底：tar 组件的 data 目录（旧布局 data/<name> 与 ADR-0026 新布局 private/public 都试）"""
    dest.mkdir(parents=True, exist_ok=True)
    covered = []
    for candidate in (DATA_ROOT / "private" / tool["name"], DATA_ROOT / tool["name"],
                      DATA_ROOT / "public" / tool["name"]):
        if candidate.is_dir():
            skipped = []
            with tarfile.open(dest / f"{candidate.name}.tar.gz", "w:gz") as tar:
                for root, _, files in os.walk(candidate):
                    for fn in files:
                        fp = Path(root) / fn
                        try:
                            ti = tar.gettarinfo(str(fp), arcname=str(fp.relative_to(candidate.parent)))
                            if ti.issym() or ti.islnk():
                                skipped.append(fn)
                                continue
                            with open(fp, "rb") as fh:
                                tar.addfile(ti, fh)
                        except OSError:
                            skipped.append(fn)
            covered.append(str(candidate) + (f"（{len(skipped)} 个跨平台残留已跳过）" if skipped else ""))
    return {"covers": covered, "declared": False, "skipped": not covered}


def _default_restore(tool: dict, src: Path) -> dict:
    restored = []
    for tar_path in src.glob("*.tar.gz"):
        target = DATA_ROOT / tar_path.stem.replace(".tar", "")
        with tarfile.open(tar_path) as tar:
            tar.extractall(DATA_ROOT, filter="data")
        restored.append(str(target))
    return {"restored": restored, "declared": False}


def _topo_order(manifests: dict) -> list[str]:
    """按 requires 拓扑排序（被依赖者优先）；环则按名字兜底"""
    order, seen = [], set()

    def visit(name: str):
        if name in seen:
            return
        seen.add(name)
        for dep in manifests[name].get("requires", []):
            if dep in manifests:
                visit(dep)
        order.append(name)

    for name in sorted(manifests):
        visit(name)
    return order


def backup(out_dir: Path | None = None) -> dict:
    """一键备份（ADR-0015 的一键实现，组件化形态）"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    bundle = (out_dir or BACKUPS_DIR) / ts
    bundle.mkdir(parents=True, exist_ok=True)

    tools = load_tools()
    manifests, results = {}, {}
    for t in tools:
        hook = _hook_path(t)
        dest = bundle / t["name"]
        if hook:
            dest.mkdir(parents=True, exist_ok=True)
            m = _run_hook(hook, "manifest", dest)
            manifests[t["name"]] = m if isinstance(m, dict) else {}
        else:
            manifests[t["name"]] = {"requires": []}

    for name in _topo_order(manifests):
        tool = next(t for t in tools if t["name"] == name)
        hook = _hook_path(tool)
        dest = bundle / name
        if hook:
            results[name] = _run_hook(hook, "backup", dest)
            results[name]["declared"] = True
        else:
            results[name] = _default_backup(tool, dest)

    # supervisor 自身数据（不在组件注册表）：private/chronicler + public
    sup = bundle / "chronicler"
    sup.mkdir(exist_ok=True)
    covered = []
    for cand in (Cfg.DATA, Cfg.PUBLIC):
        if cand.is_dir():
            with tarfile.open(sup / f"{cand.name}.tar.gz", "w:gz") as tar:
                tar.add(cand, arcname=cand.name)
            covered.append(str(cand))
    results["chronicler"] = {"covers": covered, "declared": True, "note": "supervisor 自身数据"}

    top = {"timestamp": ts, "supervisor": "chronicler", "components": results}
    (bundle / "manifest.json").write_text(json.dumps(top, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return {"ok": True, "bundle": str(bundle), "components": results}


def restore(src: Path) -> dict:
    manifest_path = src / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"备份包缺少 manifest.json：{src}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tools = {t["name"]: t for t in load_tools()}
    results = {}
    # 逆拓扑序恢复
    for name in reversed(list(manifest["components"].keys())):
        tool = tools.get(name)
        if not tool:
            results[name] = {"skipped": True, "reason": "组件未注册"}
            continue
        hook = _hook_path(tool)
        comp_src = src / name
        if not comp_src.is_dir():
            results[name] = {"skipped": True, "reason": "备份包中无此组件"}
            continue
        results[name] = _run_hook(hook, "restore", comp_src) if hook else _default_restore(tool, comp_src)
    return {"ok": True, "components": results}
