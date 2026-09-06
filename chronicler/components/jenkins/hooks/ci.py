"""Jenkins CI 能力：last-build <job_url> —— 最近一次构建状态（ADR-0027 能力脚本）。

凭据与 API 路径知识均属本组件。stdout 末行输出 JSON：
{"ok": true, "number": N, "result": "SUCCESS", "timestamp": ...}
"""
import json
import os
import sys
from urllib.parse import urlparse

import httpx


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "last-build":
        _out({"ok": False, "error": "用法: ci.py last-build <job_url>"}, 2)
    url = sys.argv[2].rstrip("/")
    u = urlparse(url)
    host = u.hostname or ""
    # 宿主回源：*.localhost 直连 127.0.0.1 + Host 头（容器内 *.localhost 强制回环）
    base = "http://127.0.0.1" if host.endswith(".localhost") else f"{u.scheme}://{u.netloc}"
    headers = {"Host": host} if host.endswith(".localhost") else {}
    auth = (os.environ.get("JENKINS_ADMIN_ID", ""), os.environ.get("JENKINS_ADMIN_PASSWORD", ""))
    try:
        with httpx.Client(timeout=8, trust_env=False) as client:
            r = client.get(f"{base}{u.path}/lastBuild/api/json?tree=number,result,timestamp,url",
                           headers=headers, auth=auth if auth[1] else None)
    except Exception as e:  # noqa: BLE001
        _out({"ok": False, "error": f"unreachable: {e}"}, 1)
    if r.status_code != 200:
        _out({"ok": False, "error": f"HTTP {r.status_code}"}, 1)
    b = r.json()
    _out({"ok": True, "number": b.get("number"), "result": b.get("result"),
          "timestamp": b.get("timestamp"), "url": b.get("url")})


if __name__ == "__main__":
    main()
