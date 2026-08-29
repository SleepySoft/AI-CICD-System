"""Chronicler CLI：
  python -m chronicler serve              启动 supervisor（默认 0.0.0.0:8600）
  python -m chronicler create-admin       交互创建 admin 账号
  python -m chronicler backup [目录]       组件化一键备份（ADR-0027）
  python -m chronicler restore <备份目录>  恢复
"""
import sys

# 兼容直接按文件运行/调试（IDE 脚本模式无包上下文，相对导入会炸）：
# 手动声明包身份并把仓库根加入 sys.path，等价于 python -m chronicler
if not __package__:
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "chronicler"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        import uvicorn
        from .app.config import Cfg
        Cfg.ensure_dirs()
        uvicorn.run("chronicler.app.main:app", host=Cfg.HOST, port=Cfg.PORT)
    elif cmd == "backup":
        from pathlib import Path
        from .app.backup import backup
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        result = backup(out)
        print(f"备份完成：{result['bundle']}")
        for name, r in result["components"].items():
            state = "跳过" if r.get("skipped") else ("失败: " + r.get("error", "") if r.get("error") else "OK")
            declared = "" if r.get("declared", True) else "（兜底策略）"
            print(f"  {name}: {state}{declared}")
    elif cmd == "restore":
        if len(sys.argv) < 3:
            sys.exit("用法: python -m chronicler restore <备份目录>")
        from pathlib import Path
        from .app.backup import restore
        result = restore(Path(sys.argv[2]))
        for name, r in result["components"].items():
            print(f"  {name}: {r}")
    elif cmd == "create-admin":
        import getpass
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
