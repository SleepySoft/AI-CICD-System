"""Chronicler CLI：
  python -m chronicler serve              启动 supervisor（默认 0.0.0.0:8600）
  python -m chronicler create-admin       交互创建 admin 账号
"""
import getpass
import sys


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        import uvicorn
        from .app.config import Cfg
        Cfg.ensure_dirs()
        uvicorn.run("chronicler.app.main:app", host=Cfg.HOST, port=Cfg.PORT)
    elif cmd == "create-admin":
        from .app import db
        from .app.auth import hash_password
        db.init()
        username = input("admin 用户名: ").strip()
        if not username:
            sys.exit("用户名不能为空")
        if db.q1("SELECT id FROM users WHERE username=?", (username,)):
            sys.exit(f"用户 {username} 已存在")
        password = getpass.getpass("密码: ")
        if len(password) < 6:
            sys.exit("密码至少 6 位")
        db.execute("INSERT INTO users(username, password_hash, role, created_at)"
                   " VALUES (?,?,'admin',strftime('%s','now'))", (username, hash_password(password)))
        print(f"admin {username} 已创建")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
