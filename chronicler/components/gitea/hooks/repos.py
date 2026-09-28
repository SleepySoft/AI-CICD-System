"""Gitea 仓库能力：ensure 建仓；delete 仅删本组件管理的 Shadow 仓。

凭据、地址、端口知识均属本组件（plugin.yaml url + setup.yaml 字段）。
stdout 末行输出 JSON {"ok": true, "clone_url": "..."}。
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in {"ensure", "delete"} or len(sys.argv) != 3:
        _out({"ok": False, "error": "用法: repos.py ensure|delete <repo_name>"}, 2)
    repo = sys.argv[2]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", repo):
        _out({"ok": False, "error": "仓库名无效"}, 2)
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
    if action == "delete":
        expected = os.environ.get("CHRONICLER_EXPECTED_REPO_URL", "")
        parsed = urlsplit(expected)
        managed = urlsplit(f"{base}/{user}/{repo}.git")
        if (not repo.endswith("-shadow") or repo == "-shadow" or "/" in repo or
                parsed.query or parsed.fragment or
                (parsed.scheme, parsed.hostname, parsed.port, parsed.path) !=
                (managed.scheme, managed.hostname, managed.port, managed.path)):
            _out({"ok": False, "error": "目标不是本组件管理的 Shadow 仓"}, 2)
        with httpx.Client(timeout=10, trust_env=False) as client:
            r = client.delete(f"{api}/repos/{user}/{repo}", headers=headers, auth=auth)
        if r.status_code not in (204, 404):
            _out({"ok": False, "error": f"删仓失败：HTTP {r.status_code}"}, 1)
        _out({"ok": True, "deleted": r.status_code == 204})
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
