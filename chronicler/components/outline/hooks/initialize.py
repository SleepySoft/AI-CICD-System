"""幂等同步 Outline 自有的 Keycloak OIDC 客户端。"""
import json
import os
import sys

import docker

KC = os.environ["CHRONICLER_DEPENDENCY_KEYCLOAK_CONTAINER"]
KCADM = "/opt/keycloak/bin/kcadm.sh"


def run(args):
    result = docker.from_env().containers.get(KC).exec_run([KCADM, *args], user="keycloak")
    text = result.output.decode("utf-8", errors="replace")
    if result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def login():
    run(["config", "credentials", "--server", "http://localhost:8080", "--realm", "master",
         "--user", os.environ.get("KEYCLOAK_ADMIN", "admin"),
         "--password", os.environ["KEYCLOAK_ADMIN_PASSWORD"]])


def client(required=True):
    clients = json.loads(run(["get", "clients", "-r", "aisystem", "-q", "clientId=outline"]))
    if required and not clients:
        raise RuntimeError("Outline 的 OIDC 客户端尚未配置")
    return clients[0] if clients else None


def check():
    login()
    client()


def apply():
    login()
    current = client(required=False)
    domain = os.environ.get("BASE_DOMAIN", "localhost")
    root = f"http://kb.{domain}"
    values = {"clientId": "outline", "enabled": True, "protocol": "openid-connect",
              "publicClient": False, "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
              "secret": os.environ["OIDC_OUTLINE_SECRET"],
              "redirectUris": [root + "/auth/oidc.callback", root + "/*"],
              "webOrigins": [root], "attributes": {"post.logout.redirect.uris": root + "/*"}}
    args = (["update", f"clients/{current['id']}"] if current else ["create", "clients"])
    args.extend(["-r", "aisystem"])
    for key, value in values.items():
        args.extend(["-s", f"{key}={json.dumps(value) if isinstance(value, (list, dict, bool)) else value}"])
    run(args)


if __name__ == "__main__":
    (apply if sys.argv[1] == "apply" else check)()
    print(json.dumps({"ok": True}))