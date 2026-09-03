"""初始化模块自有 SQLite 状态；不把初始化字段散入业务表。"""
import json
import sqlite3
import time
from contextlib import contextmanager

from ..config import Cfg

SCHEMA = """
CREATE TABLE IF NOT EXISTS installation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL DEFAULT 1,
    lifecycle TEXT NOT NULL DEFAULT 'bootstrap',
    bootstrap_token_hash TEXT DEFAULT '',
    bootstrap_closed_at REAL,
    active_run_id INTEGER,
    completed_plan_hash TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_drafts (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision INTEGER NOT NULL DEFAULT 1,
    stage TEXT NOT NULL DEFAULT 'preflight',
    profile TEXT NOT NULL DEFAULT 'recommended',
    selections_json TEXT NOT NULL DEFAULT '[]',
    values_json TEXT NOT NULL DEFAULT '{}',
    secret_presence_json TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_revision INTEGER NOT NULL,
    environment_fingerprint TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    confirmed_at REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    finished_at REAL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS setup_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    component TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_hash TEXT NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 0,
    error_class TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    started_at REAL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS setup_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    step_id INTEGER,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    at REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    Cfg.DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Cfg.db_path(), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def transaction():
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema():
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def one(sql: str, args: tuple = ()) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(sql, args).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def all_(sql: str, args: tuple = ()) -> list[dict]:
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def execute(sql: str, args: tuple = ()) -> int:
    conn = _connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def installation() -> dict | None:
    init_schema()
    return one("SELECT * FROM installation WHERE id=1")


def ensure_installation(lifecycle: str = "bootstrap") -> dict:
    init_schema()
    now = time.time()
    execute("INSERT OR IGNORE INTO installation(id,lifecycle,created_at,updated_at) VALUES(1,?,?,?)",
            (lifecycle, now, now))
    return installation()


def get_draft() -> dict:
    init_schema()
    row = one("SELECT * FROM setup_drafts WHERE id=1")
    if not row:
        now = time.time()
        execute("INSERT INTO setup_drafts(id,updated_at) VALUES(1,?)", (now,))
        row = one("SELECT * FROM setup_drafts WHERE id=1")
    return {
        "revision": row["revision"], "stage": row["stage"], "profile": row["profile"],
        "selections": json.loads(row["selections_json"]),
        "values": json.loads(row["values_json"]),
        "secrets": json.loads(row["secret_presence_json"]),
        "updated_at": row["updated_at"],
    }


def save_draft(stage: str, profile: str, selections: list[str], values: dict,
               secret_presence: dict) -> dict:
    now = time.time()
    with transaction() as conn:
        row = conn.execute("SELECT revision FROM setup_drafts WHERE id=1").fetchone()
        revision = (row[0] + 1) if row else 1
        conn.execute("""INSERT INTO setup_drafts
            (id,revision,stage,profile,selections_json,values_json,secret_presence_json,updated_at)
            VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,
            stage=excluded.stage,profile=excluded.profile,selections_json=excluded.selections_json,
            values_json=excluded.values_json,secret_presence_json=excluded.secret_presence_json,
            updated_at=excluded.updated_at""",
            (revision, stage, profile, json.dumps(selections), json.dumps(values),
             json.dumps(secret_presence), now))
    return get_draft()


def add_event(run_id: int, level: str, event_type: str, message: str,
              step_id: int | None = None, data: dict | None = None):
    execute("""INSERT INTO setup_events(run_id,step_id,level,event_type,message,data_json,at)
             VALUES(?,?,?,?,?,?,?)""",
            (run_id, step_id, level, event_type, message,
             json.dumps(data or {}, ensure_ascii=False), time.time()))