"""只读检查全部账号的加密认证字段；不会打印密钥或令牌。"""
import json
import os
from pathlib import Path

import docker


def check():
    source = (Path(__file__).resolve().parent.parent / "auth-health.js").read_text(encoding="utf-8")
    container = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-outline-1")
    try:
        result = docker.from_env().containers.get(container).exec_run(["node", "-e", source])
        lines = result.output.decode("utf-8", errors="replace").strip().splitlines()
        payload = json.loads(lines[-1])
        print(json.dumps(payload, ensure_ascii=False))
        return result.exit_code
    except Exception as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(check())
