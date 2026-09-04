#!/usr/bin/env python3
"""安全清除 Chronicler Web 初始化状态，让初始化向导从欢迎页重新开始。

该脚本只清除初始化模块的草稿、计划、运行步骤、事件和引导会话，并重新开放
bootstrap 引导。它不会删除 .env、Chronicler 用户/工程、组件容器或 data 下的
组件业务数据；已经部署的组件会在重新初始化时被检查并尽量复用。

用法（必须在交互终端运行）：
    python scripts/reset-initialization.py

如 CHRONICLER_DATA 指向自定义目录，脚本会遵循该环境变量。
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "private" / "chronicler"
INITIALIZATION_TABLES = (
    "setup_events",
    "setup_steps",
    "setup_runs",
    "setup_plans",
    "setup_drafts",
)
BUSINESS_TABLES = ("users", "projects", "task_runs")


def data_dir() -> Path:
    configured = os.environ.get("CHRONICLER_DATA")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DATA.resolve()


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def counts(conn: sqlite3.Connection, tables: set[str]) -> dict[str, int]:
    names = INITIALIZATION_TABLES + BUSINESS_TABLES
    return {
        name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for name in names if name in tables
    }


def installation_summary(conn: sqlite3.Connection, tables: set[str]) -> str:
    if "installation" not in tables:
        return "无 initialization 记录（首次启动会自动创建）"
    row = conn.execute(
        "SELECT lifecycle, bootstrap_closed_at, active_run_id FROM installation WHERE id=1"
    ).fetchone()
    if not row:
        return "installation 表为空（首次启动会自动创建）"
    return (f"lifecycle={row[0]}, closed={bool(row[1])}, "
            f"active_run_id={row[2] or '无'}")


def confirm_three_times(db_path: Path) -> None:
    print("\n【第一次确认：确认影响范围】")
    print("  将清除：初始化草稿、计划、运行步骤、事件、完成标记和旧引导会话。")
    print("  不会清除：.env、用户、工程、任务、组件容器以及任何组件业务数据。")
    print("  注意：若已有组件被部署，重新执行向导时会检查并复用它们，不是全新卸载。")
    answer = input("确认已理解上述范围，请输入 UNDERSTOOD：").strip()
    if answer != "UNDERSTOOD":
        raise SystemExit("输入不匹配，已取消；未修改任何数据。")

    print("\n【第二次确认：确认服务已停止】")
    print("  必须先停止 Chronicler，否则运行中的进程可能继续写入旧状态。")
    answer = input("确认 Chronicler 已停止，请输入 STOPPED：").strip()
    if answer != "STOPPED":
        raise SystemExit("输入不匹配，已取消；未修改任何数据。")

    code = secrets.token_hex(3).upper()
    print("\n【第三次确认：确认目标数据库】")
    print(f"  目标：{db_path}")
    print(f"  最终确认码：{code}")
    answer = input("请输入上面的最终确认码：").strip().upper()
    if answer != code:
        raise SystemExit("确认码不匹配，已取消；未修改任何数据。")


def backup_database(conn: sqlite3.Connection, data: Path) -> Path:
    backup_dir = data / "reset-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"chronicler-before-init-reset-{stamp}.db"
    suffix = 1
    while target.exists():
        target = backup_dir / f"chronicler-before-init-reset-{stamp}-{suffix}.db"
        suffix += 1
    backup = sqlite3.connect(target)
    try:
        conn.backup(backup)
    finally:
        backup.close()
    return target


def reset_database(db_path: Path, data: Path) -> tuple[Path | None, dict[str, int]]:
    if not db_path.is_file():
        return None, {}

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        tables = table_names(conn)
        before = counts(conn, tables)
        backup = backup_database(conn, data)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for name in INITIALIZATION_TABLES:
                if name in tables:
                    conn.execute(f'DELETE FROM "{name}"')
            if "installation" in tables:
                conn.execute(
                    """UPDATE installation
                       SET lifecycle='bootstrap', bootstrap_token_hash='',
                           bootstrap_closed_at=NULL, active_run_id=NULL,
                           completed_plan_hash='', updated_at=strftime('%s','now')
                       WHERE id=1"""
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return backup, before
    finally:
        conn.close()


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1:] in (["-h"], ["--help"]):
            print(__doc__)
            return 0
        print(f"[拒绝] 不支持的参数：{' '.join(sys.argv[1:])}", file=sys.stderr)
        print("使用 --help 查看说明。", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print("[拒绝] 此脚本必须在交互终端运行，不支持管道输入或无人值守确认。", file=sys.stderr)
        return 2

    data = data_dir()
    db_path = data / "chronicler.db"
    env_path = ROOT / ".env"
    session_key = data / "initialization" / "session.key"

    print("=" * 72)
    print("Chronicler 初始化状态清除工具")
    print("=" * 72)
    print(f"仓库/安装根：{ROOT}")
    print(f"Chronicler 数据目录：{data}")
    print(f"目标数据库：{db_path}（{'存在' if db_path.is_file() else '不存在'}）")
    print(f"配置文件：{env_path}（保留，{'存在' if env_path.is_file() else '不存在'}）")

    if db_path.is_file():
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            tables = table_names(conn)
            print(f"当前初始化状态：{installation_summary(conn, tables)}")
            current = counts(conn, tables)
            print("将清除的初始化记录：")
            for name in INITIALIZATION_TABLES:
                print(f"  - {name}: {current.get(name, 0)} 条")
            preserved = {name: current[name] for name in BUSINESS_TABLES if name in current}
            if preserved:
                print("明确保留的业务记录：")
                for name, count in preserved.items():
                    print(f"  - {name}: {count} 条")
        finally:
            conn.close()
    else:
        print("数据库尚不存在；确认后只会清除可能残留的引导会话文件。")

    confirm_three_times(db_path)

    try:
        backup, before = reset_database(db_path, data)
        session_key.unlink(missing_ok=True)
    except (OSError, sqlite3.Error) as exc:
        print(f"\n[失败] 未能完成清除：{exc}", file=sys.stderr)
        print("请确认 Chronicler 已完全停止、数据库未被占用且当前用户有写权限。", file=sys.stderr)
        return 1

    print("\n[完成] 初始化状态已清除。")
    if backup:
        print(f"安全备份：{backup}")
    if before:
        print("已删除：" + "、".join(
            f"{name} {before.get(name, 0)} 条" for name in INITIALIZATION_TABLES
        ))
    print(".env、业务数据和组件数据均未删除。")
    print("\n下一步：")
    print("  1. 启动 Chronicler：python -m chronicler serve")
    print("  2. 使用控制台新打印的 /setup#code=... 链接")
    print("  3. 浏览器按 Ctrl+F5 强制刷新后重新配置")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
