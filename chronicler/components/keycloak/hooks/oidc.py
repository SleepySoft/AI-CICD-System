"""Keycloak OIDC 客户端注册能力：upsert-client（ADR-0027 能力脚本，ADR-0047）。

凭据、容器名、realm 均为本组件自有知识。stdout 末行输出 JSON {"ok": ...}。
用法：oidc.py upsert-client <client_id> <secret> <base_url> <callback_path>
幂等：客户端不存在则创建、存在则更新密钥与回调地址；profile/email scope 缺失时补建。
"""
import json
import os
import subprocess
import sys

CONTAINER = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-keycloak-1")
ADMIN = os.environ.get("KEYCLOAK_ADMIN", "admin")
PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
REALM = "aisystem"  # 本组件镜像播种的业务 realm
KCADM = "/opt/keycloak/bin/kcadm.sh"


def _kcadm(*args, stdin: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    if stdin is not None:
        cmd.append("-i")
    cmd += [CONTAINER, KCADM, *args]
    return subprocess.run(cmd, input=stdin, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=60)


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def _login():
    r = _kcadm("config", "credentials", "--server", "http://localhost:8080",
               "--realm", "master", "--user", ADMIN, "--password", PASSWORD)
    if r.returncode != 0:
        _out({"ok": False, "error": "Keycloak 管理员认证失败"}, 1)


def _scope_id(name: str) -> str:
    r = _kcadm("get", "client-scopes", "-r", REALM, "--fields", "id,name")
    if r.returncode != 0:
        return ""
    for scope in json.loads(r.stdout):
        if scope.get("name") == name:
            return scope["id"]
    return ""


def _ensure_scope(name: str, claim: str, user_attr: str):
    """realm 模板仅预置 groups scope；profile/email 缺失时补建并挂 property 映射。"""
    if _scope_id(name):
        return
    payload = {"name": name, "protocol": "openid-connect",
               "attributes": {"include.in.token.scope": "true",
                              "display.on.consent.screen": "false"}}
    r = _kcadm("create", "client-scopes", "-r", REALM, "-f", "-", stdin=json.dumps(payload))
    if r.returncode != 0:
        _out({"ok": False, "error": f"创建 {name} scope 失败：" + (r.stderr or r.stdout).strip()[-200:]}, 1)
    mapper = {"name": claim, "protocol": "openid-connect",
              "protocolMapper": "oidc-usermodel-property-mapper",
              "config": {"user.attribute": user_attr, "claim.name": claim,
                         "jsonType.label": "String", "id.token.claim": "true",
                         "access.token.claim": "true", "userinfo.token.claim": "true"}}
    _kcadm("create", f"client-scopes/{_scope_id(name)}/protocol-mappers/models",
           "-r", REALM, "-f", "-", stdin=json.dumps(mapper))


def _client_uuid(client_id: str) -> str:
    r = _kcadm("get", "clients", "-r", REALM, "-q", f"clientId={client_id}", "--fields", "id")
    clients = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    return clients[0]["id"] if clients else ""


def _assign_scope(client_uuid: str, scope_name: str):
    sid = _scope_id(scope_name)
    if client_uuid and sid:  # 重复分配由 Keycloak 侧幂等处理
        _kcadm("update", f"clients/{client_uuid}/default-client-scopes/{sid}", "-r", REALM, "-n")


def _upsert_client(client_id: str, secret: str, base_url: str, callback_path: str) -> str:
    base = base_url.rstrip("/")
    if not callback_path.startswith("/"):
        callback_path = "/" + callback_path
    values = {"clientId": client_id, "enabled": True, "protocol": "openid-connect",
              "publicClient": False, "standardFlowEnabled": True,
              "directAccessGrantsEnabled": False, "secret": secret,
              "redirectUris": [base + callback_path, base + "/*"],
              "webOrigins": [base],
              "attributes": {"post.logout.redirect.uris": base + "/*"}}
    existing = _client_uuid(client_id)
    if existing:
        args = ["update", f"clients/{existing}", "-r", REALM]
        for key, value in values.items():
            args += ["-s", f"{key}={json.dumps(value) if isinstance(value, (list, dict, bool)) else value}"]
        r = _kcadm(*args)
        action = "updated"
    else:
        payload = {**values,
                   "defaultClientScopes": ["web-origins", "acr", "profile", "email", "roles", "groups"]}
        r = _kcadm("create", "clients", "-r", REALM, "-f", "-", stdin=json.dumps(payload))
        action = "created"
    if r.returncode != 0:
        _out({"ok": False, "error": (r.stderr or r.stdout).strip()[-200:]}, 1)
    uid = existing or _client_uuid(client_id)
    _assign_scope(uid, "profile")
    _assign_scope(uid, "email")
    return action


def main():
    if len(sys.argv) != 6 or sys.argv[1] != "upsert-client":
        _out({"ok": False,
              "error": "用法: oidc.py upsert-client <client_id> <secret> <base_url> <callback_path>"}, 2)
    _, _, client_id, secret, base_url, callback_path = sys.argv
    if not PASSWORD:
        _out({"ok": False, "error": "缺少 KEYCLOAK_ADMIN_PASSWORD（经能力执行器注入或手动提供）"}, 2)
    _login()
    _ensure_scope("profile", "preferred_username", "username")
    _ensure_scope("email", "email", "email")
    action = _upsert_client(client_id, secret, base_url, callback_path)
    _out({"ok": True, "clientId": client_id, "action": action})


if __name__ == "__main__":
    main()
