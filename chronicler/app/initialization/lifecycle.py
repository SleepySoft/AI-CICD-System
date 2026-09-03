"""初始化生命周期判定及旧实例安全收养。"""
import sqlite3
import time

from ..config import Cfg
from ..runtime import PROFILE
from . import store


def _legacy_has_users() -> bool:
    path = Cfg.db_path()
    if not path.is_file():
        return False
    conn = None
    try:
        conn = sqlite3.connect(path)
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        return bool(table and conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())
    except sqlite3.Error:
        return True  # 无法确认的存量 DB 失败关闭，不能误开 bootstrap
    finally:
        if conn is not None:
            conn.close()


def detect_mode() -> str:
    """返回 bootstrap|normal|repair；该函数不得创建业务表。"""
    legacy = _legacy_has_users()
    inst = store.installation()
    if not inst and legacy:
        now = time.time()
        store.execute("""INSERT INTO installation
            (id,lifecycle,bootstrap_closed_at,created_at,updated_at)
            VALUES(1,'legacy-adopted',?,?,?)""", (now, now, now))
        inst = store.installation()
    if not inst:
        store.ensure_installation()
        return "bootstrap"
    if not inst["bootstrap_closed_at"]:
        return "bootstrap"
    return "normal" if (PROFILE.install_root / ".env").is_file() else "repair"


def public_status() -> dict:
    inst = store.ensure_installation()
    mode = detect_mode()
    return {"mode": mode, "lifecycle": inst["lifecycle"],
            "closed": bool(inst["bootstrap_closed_at"]),
            "active_run_id": inst["active_run_id"]}