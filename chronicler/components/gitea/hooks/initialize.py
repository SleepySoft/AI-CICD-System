"""幂等创建 Gitea 管理员和 Keycloak 认证源。"""
import os
import sys

import docker

C = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-gitea-1")


def exec_(args, check=True):
    result = docker.from_env().containers.get(C).exec_run(["gitea", *args], user="git")
    text = result.output.decode("utf-8", errors="replace")
    if check and result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def check():
    auth = exec_(["admin", "auth", "list"], check=False)
    users = exec_(["admin", "user", "list", "--admin"], check=False)
    if "keycloak" not in auth or os.environ.get("GITEA_ADMIN_USER", "gitea_admin") not in users:
        raise RuntimeError("Gitea 管理员或 Keycloak 认证源尚未配置")


def apply():
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