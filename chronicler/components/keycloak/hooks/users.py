"""Keycloak 用户管理能力：reset-password（ADR-0027 能力脚本，由核心通用执行器调用）。

凭据、容器名、realm 均为本组件自有知识。stdout 末行输出 JSON {"ok": ...}。
用法：users.py reset-password <username> <new_password> [--temporary|--permanent]
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
    return subprocess.run(["docker", "exec", CONTAINER, "/opt/keycloak/bin/kcadm.sh", *args],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=60)


def _out(payload: dict, code: int = 0):
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    if len(sys.argv) < 4 or sys.argv[1] != "reset-password":
        _out({"ok": False, "error": "用法: users.py reset-password <username> <password> [--temporary|--permanent]"}, 2)
    username, password = sys.argv[2], sys.argv[3]
    temporary = "--permanent" not in sys.argv[4:]
    r = _kcadm("config", "credentials", "--server", "http://localhost:8080",
               "--realm", "master", "--user", ADMIN, "--password", PASSWORD)
    if r.returncode != 0:
        _out({"ok": False, "error": "Keycloak 管理员认证失败"}, 1)
    args = ["set-password", "-r", REALM, "--username", username, "--new-password", password]
    if temporary:
        args.append("--temporary")
    r = _kcadm(*args)
    if r.returncode != 0:
        _out({"ok": False, "error": (r.stderr or r.stdout).strip()[-200:]}, 1)
    _out({"ok": True, "username": username, "temporary": temporary})


if __name__ == "__main__":
    main()
