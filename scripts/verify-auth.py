#!/usr/bin/env python3
"""生产登录链巡检（FR-ENV-003 认证层补充）：逐组件验证「可达 + 可登录」。

数据源：chronicler/components/<name>/plugin.yaml 的 auth 自述块（kind: basic/bearer/token-grant/sso）；
凭据从秘密库渲染（只读使用，登录仅建会话）；SSO 全链路用 realm 测试账号 dev 真登录。

与 scripts/verify-pages.py 的关系：那个只验入口 HTTP 状态；本脚本验认证链路。
用法: python scripts/verify-auth.py     （Windows/WSL 均可；需 docker 与秘密库主密钥可读）
注意: httpx 必须 trust_env=False——Windows 系统代理（Clash）会劫持 127.0.0.1 请求返 502（2026-09-16 实测）。
"""
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chronicler.app.runtime import PROFILE
from chronicler.app.vault import sync as vault_sync

BASE = "http://127.0.0.1"
SSO_HOST = "sso.localhost"
SSO_USER = "dev"       # realm aisystem 测试账号（realm 模板内置）
SSO_PASS = "dev123"
TIMEOUT = 12

results = []


def report(name, ok, detail, skip=False):
    results.append((ok, name, detail, skip))
    mark = "SKIP" if skip else ("PASS" if ok else "FAIL")
    print(f"[{mark}] {name:26s} {detail}")


def plant_cookies(client, r):
    """手动栽种 Set-Cookie：组件常带 Domain=<真实域名>/Secure 属性（浏览器在真实域名/localhost 下
    正常，httpx 严格按 RFC 拒收）——测试侧统一落到 127.0.0.1 非 secure。"""
    for sc in r.headers.get_list("set-cookie"):
        parts = [p.strip() for p in sc.split(";")]
        if "=" not in parts[0]:
            continue
        name, value = parts[0].split("=", 1)
        if not value:
            continue
        path = "/"
        for a in parts[1:]:
            if a.lower().startswith("path="):
                path = a[5:]
        client.cookies.set(name, value, domain="127.0.0.1", path=path)


def get(client, url, defhost):
    """请求并保持 Host 语义：绝对 URL 的域名只作 Host 头，实际都打 127.0.0.1"""
    p = urlsplit(url)
    host = p.netloc or defhost
    u = BASE + (p.path or "/") + (f"?{p.query}" if p.query else "")
    r = client.get(u, headers={"Host": host})
    plant_cookies(client, r)
    return r, host


def sso_flow(name, host, oidc_path, verify):
    client = httpx.Client(follow_redirects=False, timeout=TIMEOUT, trust_env=False)
    r, _ = get(client, oidc_path, host)
    loc = r.headers.get("location", "")
    if r.status_code not in (301, 302, 303, 307, 308) or "realms/aisystem" not in loc:
        return report(name, False, f"OIDC 未跳 keycloak：{r.status_code} {loc[:80]}")
    # keycloak 登录页 + 表单真登录
    r, _ = get(client, loc, SSO_HOST)
    if r.status_code != 200:
        return report(name, False, f"keycloak 登录页 {r.status_code}（客户端未注册/配置错误）")
    m = re.search(r'action="([^"]+)"', r.text)
    if not m:
        return report(name, False, "keycloak 登录页无表单")
    p = urlsplit(m.group(1).replace("&amp;", "&"))
    r = client.post(BASE + p.path + f"?{p.query}", headers={"Host": SSO_HOST},
                    data={"username": SSO_USER, "password": SSO_PASS})
    plant_cookies(client, r)
    if r.status_code != 302:
        return report(name, False, f"keycloak 认证未通过：{r.status_code}")
    # 回调组件 + 跟随内部跳转
    r, h = get(client, r.headers["location"], host)
    for _ in range(5):
        loc = r.headers.get("location", "")
        if r.status_code not in (301, 302, 303, 307, 308) or not loc:
            break
        if "notice=" in loc:  # outline 风格错误提示
            return report(name, False, f"组件回调报错：{loc[:80]}")
        r, h = get(client, loc, h)
    if "link_account" in (r.request.url.path + r.headers.get("location", "")):
        return report(name, False, "停在账号关联页（自动建号未生效）")
    # 会话校验
    if verify.startswith("POST "):
        r = client.post(BASE + verify[5:], headers={"Host": h}, content=b"")
    else:
        r, h = get(client, verify, h)
    ok = r.status_code == 200
    detail = f"SSO 全链路 {'OK（会话已建立）' if ok else f'会话校验 {r.status_code}'}"
    if name.startswith("gitea") and ok is False and r.status_code in (301, 302, 303):
        detail += "（未登录被跳走）"
    report(name, ok, detail)


def main():
    rendered = vault_sync.resolve_env_text((PROFILE.install_root / ".env").read_text(encoding="utf-8"))
    env = dict(l.split("=", 1) for l in rendered.splitlines() if "=" in l and not l.startswith("#"))

    comp_dir = PROFILE.install_root / "chronicler" / "components"
    for d in sorted(comp_dir.iterdir()):
        plugin_path = d / "plugin.yaml"
        if not plugin_path.is_file():
            continue
        plugin = yaml.safe_load(plugin_path.read_text(encoding="utf-8")) or {}
        name, url, auths = plugin.get("name", d.name), plugin.get("url") or "", plugin.get("auth") or []
        if not url:
            continue
        host = urlsplit(url).netloc
        # 未运行组件：入口不可达属预期，单列 skip
        import subprocess
        st = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}",
                             plugin.get("container", "")],
                            capture_output=True, text=True)
        if st.stdout.strip() != "running":
            report(f"{name}", True, "容器未运行（autostart 外/未部署）", skip=True)
            continue
        if not auths:
            try:
                r = httpx.get(BASE + (urlsplit(url).path or "/"), headers={"Host": host},
                              timeout=TIMEOUT, trust_env=False)
                report(f"{name} 入口", r.status_code in (200, 301, 302, 401, 403), f"{r.status_code}")
            except Exception as e:
                report(f"{name} 入口", False, f"{type(e).__name__}: {e}")
            continue
        for a in auths:
            kind = a.get("kind")
            label = f"{name} {kind}"
            try:
                if kind == "basic":
                    r = httpx.get(BASE + a["verify"], headers={"Host": host},
                                  auth=(env.get(a["user_field"], ""), env.get(a["secret_field"], "")),
                                  timeout=TIMEOUT, trust_env=False)
                    report(label, r.status_code == 200, f"{a['verify']} {r.status_code}")
                elif kind == "bearer":
                    r = httpx.get(BASE + a["verify"], headers={"Host": host,
                                  "Authorization": f"Bearer {env.get(a['secret_field'], '')}"},
                                  timeout=TIMEOUT, trust_env=False)
                    report(label, r.status_code == 200, f"{a['verify']} {r.status_code}")
                elif kind == "token-grant":
                    realm = a.get("realm", "master")
                    r = httpx.post(BASE + f"/realms/{realm}/protocol/openid-connect/token",
                                   headers={"Host": host},
                                   data={"grant_type": "password", "client_id": "admin-cli",
                                         "username": env.get(a["user_field"], ""),
                                         "password": env.get(a["secret_field"], "")},
                                   timeout=TIMEOUT, trust_env=False)
                    report(label, r.status_code == 200, f"token 端点 {r.status_code}")
                elif kind == "sso":
                    sso_flow(label, host, a["oidc_path"], a.get("verify", "/"))
                else:
                    report(label, True, f"未知 kind={kind}，跳过", skip=True)
            except Exception as e:
                report(label, False, f"{type(e).__name__}: {e}")

    failed = sum(1 for ok, _, _, skip in results if not ok and not skip)
    passed = sum(1 for ok, _, _, skip in results if ok and not skip)
    skipped = sum(1 for _, _, _, skip in results if skip)
    print(f"\n{passed} 通过，{failed} 失败，{skipped} 跳过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
