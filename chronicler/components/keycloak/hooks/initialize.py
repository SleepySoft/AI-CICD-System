"""幂等创建/更新 Chronicler 与 Gitea OIDC 客户端。"""
import json
import os
import sys

import docker

CONTAINER = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-keycloak-1")
KCADM = "/opt/keycloak/bin/kcadm.sh"


def run(args, check=True):
    container = docker.from_env().containers.get(CONTAINER)
    result = container.exec_run([KCADM, *args], user="keycloak")
    text = result.output.decode("utf-8", errors="replace")
    if check and result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def login():
    run(["config", "credentials", "--server", "http://localhost:8080", "--realm", "master",
         "--user", os.environ.get("KEYCLOAK_ADMIN", "admin"), "--password",
         os.environ["KEYCLOAK_ADMIN_PASSWORD"]])


def find(client_id):
    data = json.loads(run(["get", "clients", "-r", "aisystem", "-q", f"clientId={client_id}"]))
    return data[0] if data else None


def desired(client_id, secret, root):
    callback = "/api/auth/oidc/callback" if client_id == "chronicler" else "/user/oauth2/keycloak/callback"
    return {"clientId": client_id, "enabled": True, "protocol": "openid-connect",
            "publicClient": False, "secret": secret, "standardFlowEnabled": True,
            "directAccessGrantsEnabled": False,
            "redirectUris": [root + callback, root + "/*"], "webOrigins": [root],
            "defaultClientScopes": ["web-origins", "acr", "profile", "email", "roles", "groups"]}


def upsert(client_id, secret, root):
    config = desired(client_id, secret, root)
    current = find(client_id)
    if current:
        args = ["update", f"clients/{current['id']}", "-r", "aisystem"]
        for key in ("enabled", "protocol", "publicClient", "secret", "standardFlowEnabled",
                    "directAccessGrantsEnabled", "redirectUris", "webOrigins"):
            value = json.dumps(config[key]) if isinstance(config[key], (bool, list)) else config[key]
            args.extend(["-s", f"{key}={value}"])
        run(args)
        return
    args = ["create", "clients", "-r", "aisystem", "-s", f"clientId={client_id}",
            "-s", "enabled=true", "-s", "protocol=openid-connect", "-s", "publicClient=false",
            "-s", f"secret={secret}", "-s", "standardFlowEnabled=true",
            "-s", "directAccessGrantsEnabled=false",
            "-s", f"redirectUris={json.dumps(config['redirectUris'])}",
            "-s", f"webOrigins={json.dumps([root])}"]
    run(args)


def check():
    login()
    missing = [client_id for client_id in ("chronicler", "gitea") if not find(client_id)]
    if missing:
        raise RuntimeError("OIDC 客户端尚未创建：" + "、".join(missing))


def apply():
    login()
    domain = os.environ.get("BASE_DOMAIN", "localhost")
    upsert("chronicler", os.environ["CHRONICLER_OIDC_SECRET"], f"http://app.{domain}")
    upsert("gitea", os.environ["OIDC_GITEA_SECRET"], f"http://git.{domain}")


if __name__ == "__main__":
    (apply if sys.argv[1] == "apply" else check)()
    print(json.dumps({"ok": True}))