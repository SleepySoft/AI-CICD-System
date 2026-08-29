"""组件测试器（FR-MGR-023）：契约校验 + 隔离沙箱部署测试

隔离原则：独立 compose 项目名（chronicle-test）+ 独立临时数据目录，
不触碰正式实例的容器名/网络/data/。组件可提供 hooks/test.py 自测钩子（优先于通用测试）。
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from .config import PKG_ROOT
from .tools import load_tools

REPO = PKG_ROOT.parent
TEST_PROJECT = "chronicle-test"
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
        r = subprocess.run([sys.executable, str(hook), "manifest"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        try:
            m = json.loads(r.stdout.strip().splitlines()[-1])
            if "covers" not in m:
                problems.append("backup 钩子 manifest 缺 covers 字段")
        except (json.JSONDecodeError, IndexError):
            problems.append("backup 钩子 manifest 未输出合法 JSON")
    return problems


def deploy_test(tool: dict, timeout: int = 300) -> dict:
    """隔离沙箱部署测试：独立项目名 + 临时数据目录，起 → 等 healthy → 销毁"""
    if tool["driver"] != "docker":
        return {"ok": True, "note": "非 docker 组件，跳过部署测试"}
    service = tool.get("compose_service") or tool["name"]
    data_root = Path(tempfile.mkdtemp(prefix=f"chronicle-test-{tool['name']}-"))
    env = {**__import__("os").environ, "COMPOSE_PROJECT_NAME": TEST_PROJECT,
           "DATA_ROOT": str(data_root), "HTTP_PORT": "18080"}
    log = []

    def run(*args, wait=None):
        r = subprocess.run(["docker", "compose", *args], cwd=str(REPO), env=env,
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=wait or 600)
        log.append((r.stdout + r.stderr).strip()[-300:])
        return r.returncode

    try:
        if run("up", "-d", service) != 0:
            return {"ok": False, "stage": "up", "log": log[-1]}
        deadline = time.time() + timeout
        container = f"{TEST_PROJECT}-{service}-1"
        while time.time() < deadline:
            r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", container],
                               capture_output=True, text=True)
            status = r.stdout.strip()
            if "healthy" in status or status == "running":  # 无健康检查的容器以 running 为准
                return {"ok": True, "container": container}
            if "exited" in status or "dead" in status:
                return {"ok": False, "stage": "health", "log": status}
            time.sleep(5)
        return {"ok": False, "stage": "health-timeout", "log": log[-1]}
    finally:
        run("down", "-v")  # 销毁沙箱（容器+网络+卷），不碰正式实例
        subprocess.run(["docker", "rm", "-f", f"{TEST_PROJECT}-{service}-1"],
                       capture_output=True)


def test_component(name: str, deploy: bool = False, timeout: int = 300) -> dict:
    tool = next((t for t in load_tools() if t["name"] == name), None)
    if not tool:
        return {"name": name, "ok": False, "problems": ["组件未注册"]}
    problems = check_contract(tool)
    result = {"name": name, "ok": not problems, "problems": problems}

    hook = Path(tool.get("_dir", "")) / "hooks" / "test.py"
    if hook.is_file():
        r = subprocess.run([sys.executable, str(hook)], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        result["selftest"] = {"exit": r.returncode, "output": r.stdout[-500:]}
        result["ok"] = result["ok"] and r.returncode == 0
    elif deploy:
        result["deploy"] = deploy_test(tool, timeout)
        result["ok"] = result["ok"] and result["deploy"]["ok"]
    return result


def test_all(deploy: bool = False, timeout: int = 300) -> list[dict]:
    return [test_component(t["name"], deploy, timeout) for t in load_tools()]
