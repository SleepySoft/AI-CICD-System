"""Local password management TUI（FR-MGR-017）。

本模块只允许在宿主终端运行；不通过网络暴露，也不把密码写入审计、日志或报告。
"""
import getpass
import sys
import time

from . import db
from . import component_exec
from .auth import hash_password


MIN_PASSWORD_LENGTH = 6


class PasswordTUI:
    """终端菜单式密码管理器。"""

    def __init__(self, *, input_func=input, password_func=getpass.getpass,
                 output=None, backend=None, capability_runner=None):
        self.input = input_func
        self.password = password_func
        self.output = output or sys.stdout
        self.backend = backend
        self.capability_runner = capability_runner

    def run(self) -> None:
        db.init()
        self._print("Chronicler 本地密码管理")
        self._print("所有操作仅在当前终端执行，密码不会回显。")
        try:
            while True:
                self._print("\n1) 列出账号")
                self._print("2) 创建初始 admin")
                self._print("3) 重置本地密码")
                self._print("4) 重置统一登录密码")
                self._print("q) 退出")
                choice = self.input("选择: ").strip().lower()
                if choice == "1":
                    self._list_users()
                elif choice == "2":
                    self._create_admin()
                elif choice == "3":
                    self._reset_local_password()
                elif choice == "4":
                    self._reset_sso_password()
                elif choice in {"q", "quit", "exit"}:
                    self._print("已退出。")
                    return
                else:
                    self._print("无效选择。")
        finally:
            db.close()

    def _print(self, text: str = "") -> None:
        print(text, file=self.output, flush=True)

    def _backend(self) -> str:
        if self.backend is None:
            from .config import Cfg
            return Cfg.AUTH_BACKEND
        return self.backend

    def _list_users(self) -> None:
        rows = db.q("SELECT username, role, password_hash FROM users ORDER BY id")
        if not rows:
            self._print("（还没有账号）")
            return
        self._print(f"{'用户名':<24} {'角色':<8} 类型")
        for row in rows:
            source = "local" if row["password_hash"] else "oidc"
            self._print(f"{row['username']:<24} {row['role']:<8} {source}")

    def _create_admin(self) -> None:
        username = self.input("admin 用户名: ").strip()
        if not username:
            self._print("用户名不能为空。")
            return
        if db.q1("SELECT id FROM users WHERE username=?", (username,)):
            self._print(f"用户 {username} 已存在；如需改密请选择重置。")
            return
        password = self._read_password()
        if password is None:
            return
        db.execute(
            "INSERT INTO users(username, password_hash, role, created_at)"
            " VALUES (?,?,'admin',?)",
            (username, hash_password(password), time.time()),
        )
        db.audit("local-console", "password.admin_create", username)
        self._print(f"已创建本地 admin：{username}")

    def _reset_local_password(self) -> None:
        username = self.input("用户名: ").strip()
        user = db.q1("SELECT username, role FROM users WHERE username=?", (username,))
        if not user:
            self._print(f"用户 {username} 不存在。")
            return
        if self._backend() == "oidc" and user["role"] != "admin":
            self._print("OIDC 模式下普通账号由统一登录管理，请选择 4 重置统一登录密码。")
            return
        password = self._read_password()
        if password is None:
            return
        db.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (hash_password(password), username),
        )
        db.audit("local-console", "password.local_reset", username,
                 f"backend={self._backend()}")
        self._print(f"已重置本地密码：{username}")

    def _reset_sso_password(self) -> None:
        runner = self.capability_runner or component_exec.run_capability
        if not self.capability_runner and component_exec.find_capability("users.py") is None:
            self._print("当前安装没有提供统一登录重置能力（users.py）。")
            return
        username = self.input("用户名: ").strip()
        if not username:
            self._print("用户名不能为空。")
            return
        password = self._read_password()
        if password is None:
            return
        self._print("正在调用身份组件，请稍候...")
        result = runner(
            "users.py",
            ["reset-password", username, "--password-env", "CHRONICLER_IDENTITY_RESET_PASSWORD",
             "--permanent"],
            env={"CHRONICLER_IDENTITY_RESET_PASSWORD": password},
        )
        if result is None:
            self._print("统一登录组件不支持密码重置。")
            return
        if not result.get("ok"):
            self._print(f"重置失败：{result.get('error', '未知错误')}")
            return
        db.audit("local-console", "password.sso_reset", username)
        self._print(f"已重置统一登录密码：{username}")

    def _read_password(self) -> str | None:
        password = self.password("新密码: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            self._print(f"密码至少 {MIN_PASSWORD_LENGTH} 位。")
            return None
        confirm = self.password("确认新密码: ")
        if password != confirm:
            self._print("两次输入不一致。")
            return None
        return password


def main() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("密码管理 TUI 只能在本地终端交互运行")
    PasswordTUI().run()
