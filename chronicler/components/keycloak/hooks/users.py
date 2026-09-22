"""Keycloak 用户管理能力：reset-password（ADR-0027 能力脚本，由核心通用执行器调用）。

凭据、容器名、realm 均为本组件自有知识。stdout 末行输出 JSON {"ok": ...}。
用法：
  users.py reset-password <username> <new_password> [--temporary|--permanent]
  users.py reset-password <username> --password-env ENV_NAME [--temporary|--permanent]
"""
import json
import os
import subprocess
import sys

CONTAINER = os.environ.get("CHRONICLER_COMPONENT_CONTAINER", "aisystem-keycloak-1")
ADMIN = os.environ.get("KEYCLOAK_ADMIN", "admin")
PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
REALM = "aisystem"  # 本组件镜像播种的业务 realm


def _kcadm(*args) -> subprocess.CompletedProcess:
    command = ["docker", "exec", "-e", "KC_CLI_PASSWORD", CONTAINER,
               "/opt/keycloak/bin/kcadm.sh", *args]
    return subprocess.run(command, env=os.environ.copy(),
                          capture_output=True, encoding="utf-8", errors="replace", timeout=60)


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "reset-password":
        _out({"ok": False, "error": "用法: users.py reset-password <username> [<password>|--password-env NAME] [--temporary|--permanent]"}, 2)
    username = sys.argv[2]
    password = None
    password_env = None
    flags = []
    rest = sys.argv[3:]
    index = 0
    while index < len(rest):
        arg = rest[index]
        if arg == "--password-env":
            if index + 1 >= len(rest):
                _out({"ok": False, "error": "--password-env 缺少环境变量名"}, 2)
            password_env = rest[index + 1]
            index += 2
        elif arg in ("--temporary", "--permanent"):
            flags.append(arg)
            index += 1
        elif password is None:
            password = arg
            index += 1
        else:
            _out({"ok": False, "error": f"未知参数: {arg}"}, 2)
    if password is None and password_env:
        password = os.environ.get(password_env, "")
    if not password:
        _out({"ok": False, "error": "缺少新密码"}, 2)
    temporary = "--permanent" not in flags
    os.environ["KC_CLI_PASSWORD"] = PASSWORD
    r = _kcadm("config", "credentials", "--server", "http://localhost:8080",
               "--realm", "master", "--user", ADMIN)
    if r.returncode != 0:
        _out({"ok": False, "error": "Keycloak 管理员认证失败"}, 1)
    os.environ["KC_CLI_PASSWORD"] = password
    args = ["set-password", "-r", REALM, "--username", username]
    if temporary:
        args.append("--temporary")
    r = _kcadm(*args)
    if r.returncode != 0:
        _out({"ok": False, "error": (r.stderr or r.stdout).strip()[-200:]}, 1)
    _out({"ok": True, "username": username, "temporary": temporary})


if __name__ == "__main__":
    main()
