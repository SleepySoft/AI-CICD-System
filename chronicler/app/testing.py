"""组件测试器（FR-MGR-023）：契约校验 + 隔离沙箱部署测试

部署测试委托 sandbox 机制（chronicler/app/sandbox.py，五通道隔离：独立项目名/内建网络/
剥离宿主端口/临时数据目录/一次性秘密）。组件可提供 hooks/test.py 自测钩子（优先于通用测试）。
"""
import json
import subprocess
from pathlib import Path

import yaml

from .runtime import component_python
from .tools import load_tools

REQUIRED_FIELDS = {"name": str, "group": str, "desc": str, "driver": str}
DRIVERS = {"docker", "external"}


def check_contract(tool: dict) -> list[str]:
    """plugin.yaml / SKILL.md / backup 钩子契约校验，返回问题列表（空=通过）"""
    problems = []
    for field, typ in REQUIRED_FIELDS.items():
        if not isinstance(tool.get(field), typ):
            problems.append(f"缺字段或类型错误: {field}")
    if tool.get("driver") not in DRIVERS:
        problems.append(f"driver 非法: {tool.get('driver')}")
    if tool.get("driver") == "docker" and not tool.get("container"):
        problems.append("driver=docker 但未声明 container")

    d = Path(tool.get("_dir", ""))
    skill = d / "SKILL.md"
    if skill.is_file():
        head = skill.read_text(encoding="utf-8")[:500]
        if not head.startswith("---") or "name:" not in head or "description:" not in head:
            problems.append("SKILL.md 缺 frontmatter（name/description）")
    hook = d / "hooks" / "backup.py"
    if hook.is_file():
        r = subprocess.run([component_python(), str(hook), "manifest"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        try:
            m = json.loads(r.stdout.strip().splitlines()[-1])
            if "covers" not in m:
                problems.append("backup 钩子 manifest 缺 covers 字段")
        except (json.JSONDecodeError, IndexError):
            problems.append("backup 钩子 manifest 未输出合法 JSON")
    return problems


def deploy_test(tool: dict, timeout: int = 300) -> dict:
    """隔离沙箱部署测试：委托 sandbox 机制（起依赖闭包 → 等就绪 → 探针验证 → 销毁）"""
    if tool["driver"] != "docker":
        return {"ok": True, "note": "非 docker 组件，跳过部署测试"}
    from . import sandbox
    args = sandbox.argparse.Namespace(
        components=[tool["name"]], include_disabled=True, http_port=0,
        timeout=timeout, probe_timeout=min(timeout, 300), workdir=None,
        keep=False, skip_pull=True, junit=None, host_root="", probe_host="127.0.0.1")
    return {"ok": sandbox.run_sandbox(args) == 0}


def test_component(name: str, deploy: bool = False, timeout: int = 300) -> dict:
    tool = next((t for t in load_tools() if t["name"] == name), None)
    if not tool:
        return {"name": name, "ok": False, "problems": ["组件未注册"]}
    problems = check_contract(tool)
    result = {"name": name, "ok": not problems, "problems": problems}

    hook = Path(tool.get("_dir", "")) / "hooks" / "test.py"
    if hook.is_file():
        r = subprocess.run([component_python(), str(hook)], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        result["selftest"] = {"exit": r.returncode, "output": r.stdout[-500:]}
        result["ok"] = result["ok"] and r.returncode == 0
    elif deploy:
        result["deploy"] = deploy_test(tool, timeout)
        result["ok"] = result["ok"] and result["deploy"]["ok"]
    return result


def test_all(deploy: bool = False, timeout: int = 300) -> list[dict]:
    return [test_component(t["name"], deploy, timeout) for t in load_tools()]
