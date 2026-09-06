"""Gitea 仓库能力：ensure <repo_name> —— 幂等建仓并输出 clone_url（ADR-0027 能力脚本）。

凭据、地址、端口知识均属本组件（plugin.yaml url + setup.yaml 字段）。
stdout 末行输出 JSON {"ok": true, "clone_url": "..."}。
"""
import json
import os
import sys
from pathlib import Path

import httpx
import yaml


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "ensure":
        _out({"ok": False, "error": "用法: repos.py ensure <repo_name>"}, 2)
    repo = sys.argv[2]
    user = os.environ.get("GITEA_ADMIN_USER", "gitea_admin")
    password = os.environ.get("GITEA_ADMIN_PASSWORD", "")
    if not password:
        _out({"ok": False, "error": "管理员凭据未配置"}, 1)
    plugin = yaml.safe_load((Path(__file__).parent.parent / "plugin.yaml").read_text(encoding="utf-8"))
    base = (plugin.get("url") or "http://git.localhost").rstrip("/")
    host = base.split("//", 1)[1]
    # 宿主回源：*.localhost 在容器内强制回环，宿主机直连用 127.0.0.1 + Host 头
    if host.endswith(".localhost"):
        api, headers = "http://127.0.0.1/api/v1", {"Host": host}
    else:
        api, headers = f"{base}/api/v1", {}
    auth = (user, password)
    with httpx.Client(timeout=10, trust_env=False) as client:
        r = client.get(f"{api}/repos/{user}/{repo}", headers=headers, auth=auth)
        if r.status_code == 404:
            r = client.post(f"{api}/user/repos", headers=headers, auth=auth,
                            json={"name": repo, "description": "由 Chronicler 自动创建",
                                  "private": False, "auto_init": False})
            if r.status_code not in (200, 201, 409):
                _out({"ok": False, "error": f"建仓失败：HTTP {r.status_code}"}, 1)
        elif r.status_code != 200:
            _out({"ok": False, "error": f"查询失败：HTTP {r.status_code}"}, 1)
    _out({"ok": True, "clone_url": f"{base}/{user}/{repo}.git"})


if __name__ == "__main__":
    main()
