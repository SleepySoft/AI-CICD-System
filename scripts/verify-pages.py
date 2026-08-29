#!/usr/bin/env python3
"""页面可达性巡检（FR-ENV-003 补充）：所有组件入口经 Caddy 的 HTTP 状态 + SSO 重定向检查
用法: python scripts/verify-pages.py   （Windows/WSL 均可，supervisor 无关）
"""
import re
import sys
import urllib.request
from pathlib import Path

import yaml


def collect_urls():
    urls = {}
    comp_dir = Path(__file__).resolve().parent.parent / "chronicler" / "components"
    for d in sorted(comp_dir.iterdir()):
        p = d / "plugin.yaml"
        if p.is_file():
            t = yaml.safe_load(p.read_text(encoding="utf-8"))
            if t.get("url"):
                urls[t["name"]] = t["url"]
    return urls


def check(name, url):
    m = re.match(r"https?://([^/]+)(/.*)?$", url)
    host, path = m.group(1), m.group(2) or "/"
    if not host.endswith(".localhost"):
        return f"{name:20s} {url} -> 跳过（非本机域名）"
    req = urllib.request.Request(f"http://127.0.0.1{path}", headers={"Host": host})
    try:
        opener = urllib.request.build_opener(NoRedirect())
        resp = opener.open(req, timeout=5)
        code = resp.status
        loc = ""
    except urllib.error.HTTPError as e:
        code, loc = e.code, e.headers.get("Location", "")
    except Exception as e:
        return f"{name:20s} {host} -> 不可达（{type(e).__name__}）"
    sso = " →SSO" if "sso.localhost" in loc else ""
    flag = "OK " if code in (200, 302, 401, 403) else "!!!"
    return f"{flag} {name:17s} {host} -> {code}{sso}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


if __name__ == "__main__":
    failed = 0
    for line in [check(n, u) for n, u in collect_urls().items()]:
        print(line)
        if line.startswith("!!!"):
            failed += 1
    sys.exit(1 if failed else 0)
