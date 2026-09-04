"""验证 Keycloak 自有 realm；消费方客户端由各消费组件自行管理。"""
import json
import os

import docker

CONTAINER = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-keycloak-1")
KCADM = "/opt/keycloak/bin/kcadm.sh"


def run(args):
    container = docker.from_env().containers.get(CONTAINER)
    result = container.exec_run([KCADM, *args], user="keycloak")
    text = result.output.decode("utf-8", errors="replace")
    if result.exit_code:
        raise RuntimeError(text[-500:])
    return text


def login():
    run(["config", "credentials", "--server", "http://localhost:8080", "--realm", "master",
         "--user", os.environ.get("KEYCLOAK_ADMIN", "admin"), "--password",
         os.environ["KEYCLOAK_ADMIN_PASSWORD"]])


def check():
    login()
    run(["get", "realms/aisystem"])


if __name__ == "__main__":
    check()  # apply 与 check 都只验证组件随镜像导入的 realm。
    print(json.dumps({"ok": True}))
