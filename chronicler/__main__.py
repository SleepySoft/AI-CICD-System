"""Chronicler CLI：
  python -m chronicler serve              启动 supervisor（默认 0.0.0.0 + [::]:8600 双栈）
  python -m chronicler create-admin       交互创建 admin 账号
  python -m chronicler passwords          本地密码管理 TUI（创建/重置）
  python -m chronicler backup [目录]       组件化一键备份（ADR-0027）
  python -m chronicler restore <备份目录>  恢复
  python -m chronicler env render [输出文件]   从秘密库渲染完整 env（默认 stdout；ADR-0045）
    python -m chronicler setup-recover       本机显式重开初始化引导（危险操作）
  python -m chronicler test [--component X] [--deploy] [--timeout N]   组件自检（FR-MGR-023）
  python -m chronicler sandbox [选项]     隔离沙箱组件入口可达性测试（现拉现建现测现毁，FR-ENV-003）
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
        from .app.config import Cfg
        from .app.initialization.lifecycle import detect_mode
        mode = detect_mode()
        if mode == "normal":
            Cfg.require_env()
        Cfg.ensure_dirs()
        if mode == "bootstrap":
            from .app.initialization.security import issue_code
            code = issue_code()
            print("[SETUP] Chronicler 尚未初始化。请在本机浏览器打开：")
            print(f"        http://127.0.0.1:{Cfg.PORT}/setup#code={code}")
        elif mode == "repair":
            print("[ERROR] 已初始化实例缺少 .env，已进入安全修复模式；恢复 .env 后重启。",
                  file=sys.stderr)
        from .app.main import create_app
        from .app.serving import serve
        app = create_app(mode)
        serve(app, Cfg.HOST, Cfg.PORT)
    elif cmd == "test":
        from .app.testing import test_all, test_component
        deploy = "--deploy" in sys.argv
        name = sys.argv[sys.argv.index("--component") + 1] if "--component" in sys.argv else None
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1]) if "--timeout" in sys.argv else 300
        results = [test_component(name, deploy, timeout)] if name else test_all(deploy, timeout)
        failed = 0
        for r in results:
            mark = "[PASS]" if r["ok"] else "[FAIL]"
            print(f"{mark} {r['name']}")
            for p in r.get("problems", []):
                print(f"    契约: {p}")
            if r.get("deploy") and not r["deploy"].get("ok"):
                print(f"    部署: {r['deploy'].get('stage')} — {r['deploy'].get('log', '')[:120]}")
            if not r["ok"]:
                failed += 1
        print(f"\n{len(results) - failed}/{len(results)} 通过")
        sys.exit(1 if failed else 0)
    elif cmd == "sandbox":
        from .app.sandbox import main as sandbox_main
        sandbox_main(sys.argv[2:])
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
    elif cmd == "env":
        # ADR-0045：手动 compose 运维前渲染真实 env（糊化 .env 不能直接用）
        if len(sys.argv) < 3 or sys.argv[2] != "render":
            sys.exit("用法: python -m chronicler env render [输出文件]")
        from .app.initialization import catalog
        from .app.runtime import PROFILE
        from .app.vault import sync as vault_sync
        env_path = PROFILE.install_root / ".env"
        if not env_path.is_file():
            sys.exit("缺少 .env")
        rendered = vault_sync.resolve_env_text(env_path.read_text(encoding="utf-8"))
        if len(sys.argv) > 3:
            import os
            from pathlib import Path
            out = Path(sys.argv[3])
            out.write_text(rendered, encoding="utf-8", newline="\n")
            try:
                os.chmod(out, 0o600)
            except OSError:
                pass
            print(f"已渲染到 {out}（含明文秘密，用后请删除）", file=sys.stderr)
        else:
            sys.stdout.write(rendered)
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
    elif cmd == "passwords":
        from .app.password_tui import main as password_tui_main
        password_tui_main()
    elif cmd == "setup-recover":
        from .app.config import Cfg
        from .app.initialization import store
        inst = store.installation()
        if not inst or not inst["bootstrap_closed_at"]:
            sys.exit("初始化引导当前已经开放，无需恢复")
        answer = input("这会重新开放未认证初始化入口。输入 RECOVER 确认: ").strip()
        if answer != "RECOVER":
            sys.exit("已取消")
        import time
        store.execute("""UPDATE installation SET lifecycle='bootstrap',bootstrap_closed_at=NULL,
                      bootstrap_token_hash='',active_run_id=NULL,updated_at=? WHERE id=1""", (time.time(),))
        # 旧引导 cookie 在显式恢复后不得重新获得初始化权限。
        (Cfg.DATA / "initialization" / "session.key").unlink(missing_ok=True)
        try:
            from .app.db import audit
            audit("local-console", "setup.recover")
        except Exception:
            pass
        print("初始化引导已重开；请立即执行 python -m chronicler serve 并使用新引导链接。")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
