"""幂等创建 Gitea 管理员、身份服务客户端和认证源。"""
import json
import os
import sys

import docker

C = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-gitea-1")
KC = os.environ["CHRONICLER_DEPENDENCY_KEYCLOAK_CONTAINER"]
KCADM = "/opt/keycloak/bin/kcadm.sh"


def exec_(args, check=True):
    result = docker.from_env().containers.get(C).exec_run(["gitea", *args], user="git")
    text = result.output.decode("utf-8", errors="replace")
    if check and result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def kc(args):
    result = docker.from_env().containers.get(KC).exec_run([KCADM, *args], user="keycloak")
    text = result.output.decode("utf-8", errors="replace")
    if result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def configure_oidc_client():
    kc(["config", "credentials", "--server", "http://localhost:8080", "--realm", "master",
        "--user", os.environ.get("KEYCLOAK_ADMIN", "admin"),
        "--password", os.environ["KEYCLOAK_ADMIN_PASSWORD"]])
    clients = json.loads(kc(["get", "clients", "-r", "aisystem", "-q", "clientId=gitea"]))
    domain = os.environ.get("BASE_DOMAIN", "localhost")
    root = f"http://git.{domain}"
    values = {"clientId": "gitea", "enabled": True, "protocol": "openid-connect",
              "publicClient": False, "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
              "secret": os.environ["OIDC_GITEA_SECRET"],
              "redirectUris": [root + "/user/oauth2/keycloak/callback", root + "/*"],
              "webOrigins": [root], "attributes": {"post.logout.redirect.uris": root + "/*"}}
    args = (["update", f"clients/{clients[0]['id']}"] if clients else ["create", "clients"])
    args.extend(["-r", "aisystem"])
    for key, value in values.items():
        args.extend(["-s", f"{key}={json.dumps(value) if isinstance(value, (list, dict, bool)) else value}"])
    kc(args)


def check_oidc_client():
    kc(["config", "credentials", "--server", "http://localhost:8080", "--realm", "master",
        "--user", os.environ.get("KEYCLOAK_ADMIN", "admin"),
        "--password", os.environ["KEYCLOAK_ADMIN_PASSWORD"]])
    if not json.loads(kc(["get", "clients", "-r", "aisystem", "-q", "clientId=gitea"])):
        raise RuntimeError("Gitea 的 OIDC 客户端尚未配置")


def check():
    check_oidc_client()
    auth = exec_(["admin", "auth", "list"], check=False)
    users = exec_(["admin", "user", "list", "--admin"], check=False)
    if "keycloak" not in auth or os.environ.get("GITEA_ADMIN_USER", "gitea_admin") not in users:
        raise RuntimeError("Gitea 管理员或 Keycloak 认证源尚未配置")


def apply():
    configure_oidc_client()
    if "keycloak" not in exec_(["admin", "auth", "list"], check=False):
        exec_(["admin", "auth", "add-oauth", "--name", "keycloak", "--provider", "openidConnect",
               "--key", "gitea", "--secret", os.environ["OIDC_GITEA_SECRET"],
               "--auto-discover-url", "http://keycloak:8080/realms/aisystem/.well-known/openid-configuration",
               "--group-claim-name", "groups", "--admin-group", "boss"])
    username = os.environ.get("GITEA_ADMIN_USER", "gitea_admin")
    if username not in exec_(["admin", "user", "list", "--admin"], check=False):
        exec_(["admin", "user", "create", "--admin", "--username", username,
               "--password", os.environ["GITEA_ADMIN_PASSWORD"],
               "--email", f"{username}@aisystem.local", "--must-change-password=false"])


if __name__ == "__main__":
    (apply if sys.argv[1] == "apply" else check)()
    print('{"ok":true}')