"""全组件秘密漂移审计：运行中容器的秘密环境变量 vs 秘密库当前值（2026-09-16 事故后固化）。
漂移 = 按 vault 重建会得到与运行系统不同的秘密 → SSO 断链/口令失效的根因类别。
用法: python scripts/audit-secret-drift.py   （只读对比，输出哈希指纹，不打印明文）
退出码: 有漂移=1，全一致=0。
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chronicler.app.runtime import PROFILE
from chronicler.app.vault import sync as vs

r = vs.resolve_env_text((PROFILE.install_root / ".env").read_text(encoding="utf-8"))
VAULT = dict(l.split("=", 1) for l in r.splitlines() if "=" in l and not l.startswith("#"))

COMP = Path("chronicler/components")
rows = []
for comp_dir in sorted(COMP.iterdir()):
    compose = comp_dir / "compose.yml"
    if not compose.is_file():
        continue
    doc = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
    plugin = yaml.safe_load((comp_dir / "plugin.yaml").read_text(encoding="utf-8"))
    container = plugin.get("container", "")
    for svc_name, svc in (doc.get("services") or {}).items():
        env = svc.get("environment") or {}
        if not isinstance(env, dict):
            continue
        for k, v in env.items():
            m = re.fullmatch(r"\$\{([A-Z][A-Z0-9_]*)(?::[^}]*)?\}", str(v))
            if not m or m.group(1) not in VAULT:
                continue
            key = m.group(1)
            if not re.search(r"(?i)(secret|password|token|key|sharedkey)", key):
                continue
            # 容器内实际值
            out = subprocess.run(["docker", "exec", container, "printenv", k],
                                 capture_output=True, text=True)
            if out.returncode != 0:
                rows.append((comp_dir.name, key, "容器未运行/无此变量", ""))
                continue
            actual = out.stdout.strip()
            expect = VAULT[key]
            same = actual == expect
            fp = lambda s: hashlib.sha256(s.encode()).hexdigest()[:10]
            rows.append((comp_dir.name, key,
                         "一致" if same else "漂移!",
                         f"vault={fp(expect)} 容器={fp(actual)} len {len(expect)}/{len(actual)}"))

for name, key, status, detail in rows:
    print(f"[{'OK  ' if status == '一致' else 'DIFF'}] {name:16s} {key:28s} {status} {detail}")
drifted = sum(1 for r in rows if r[2] == '漂移!')
print(f"\n共审计 {len(rows)} 个秘密环境变量，漂移 {drifted} 个")
sys.exit(1 if drifted else 0)
