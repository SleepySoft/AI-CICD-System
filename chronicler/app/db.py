"""SQLite 存储层（ADR-0023：stdlib sqlite3，WAL；M2+ 可迁移 Postgres，表结构保持同名）"""
import json
import sqlite3
import threading
import time
from pathlib import Path

from .config import Cfg
from .runtime import PROFILE

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',          -- admin | user（FR-MGR-017）
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    git_url TEXT NOT NULL,                       -- 工程核心：一个 git 链接（FR-MGR-020）
    default_branch TEXT DEFAULT '',              -- 空=远端默认分支
    shadow_repo TEXT DEFAULT '',                 -- FR-MGR-013：影子库（空=自动本地建库）
    ci_url TEXT DEFAULT '',
    description TEXT DEFAULT '',
    overrides TEXT DEFAULT '{}',                 -- JSON：harness/prompt_pack 等工程级覆盖
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS task_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,                     -- 经 registry 映射到 Prompt 家族/模式
    harness TEXT DEFAULT '',                     -- harness 覆盖：''=回落工程/全局 | harness 名
    cwd TEXT DEFAULT '',                         -- 工作目录覆盖：''=harness 默认 | repo | shadow
    prompt_override TEXT DEFAULT '',             -- 非空=工程级覆盖全局模板（FR-MGR-011 版本=hash）
    schedule_cron TEXT DEFAULT '',               -- 空=仅手动；hook/联动预留 webhook 字段
    change_policy TEXT DEFAULT 'always',         -- always|repo-changed|inputs-changed（FR-MGR-028）
    change_probes TEXT DEFAULT '[]',             -- command probe 配置 JSON（FR-MGR-027）
    webhook INTEGER DEFAULT 0,                   -- 预留：push 等事件联动
    enabled INTEGER DEFAULT 1,                   -- 关闭=停止自动触发但不删配置
    created_at REAL NOT NULL,
    UNIQUE(project_id, task_type)
);
CREATE TABLE IF NOT EXISTS task_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES task_defs(id) ON DELETE SET NULL, -- 直接触发为空；任务触发关联精确基线
    project_id INTEGER NOT NULL REFERENCES projects(id),
    task_type TEXT NOT NULL,                     -- operational_reporter | project_cognitive_maintainer | custom
    status TEXT NOT NULL DEFAULT 'queued',       -- queued|running|success|failed|skipped
    trigger TEXT NOT NULL DEFAULT 'manual',
    harness TEXT NOT NULL,
    prompt_version TEXT NOT NULL,                -- 内容 hash（FR-MGR-011）
    input_snapshot TEXT DEFAULT '{}',            -- JSON：A 段输入快照（执行前冻结，§2.1.1）
    log_path TEXT DEFAULT '',
    report_path TEXT DEFAULT '',
    error TEXT DEFAULT '',
    error_class TEXT DEFAULT '',                 -- B 段：网络|配额|解析|超时|其他
    runner_env TEXT DEFAULT '',                  -- B 段：执行环境（平台+supervisor 版本）
    artifacts TEXT DEFAULT '[]',                 -- C 段：产物清单 JSON[{kind,path,action,size_bytes,commit}]
    publication TEXT DEFAULT '{}',               -- C 段：发布策略/分支/push 状态（FR-MGR-026）
    prompt_text TEXT DEFAULT '',                 -- A 段：仅 source Profile 保存渲染全文；sealed 为空
    created_by TEXT DEFAULT '',
    started_at REAL, finished_at REAL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL, action TEXT NOT NULL,
    target TEXT DEFAULT '', detail TEXT DEFAULT '',
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS vault_secrets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'infra',       -- 作用域（FR-INIT-016，默认对齐工程）
    kind TEXT NOT NULL,                        -- text | file（ADR-0042）
    secret_type TEXT DEFAULT 'password',       -- password|client-secret|encryption-key|api-token|access-key|certificate
    rotation_risk TEXT DEFAULT 'coordinated',  -- low|coordinated|critical
    summary TEXT DEFAULT '',                   -- 用途说明（透明元数据）
    owner TEXT DEFAULT '',                     -- 属主（工程/团队/人）
    expires_at REAL,                           -- 过期时间（证书/令牌，可空）
    filename TEXT DEFAULT '',                  -- kind=file 的原始文件名
    size INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL,                      -- 明文摘要（完整性验证用）
    ciphertext BLOB NOT NULL,                  -- age 密文（主密钥在 data/ 之外）
    created_by TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(scope, name)
);
CREATE TABLE IF NOT EXISTS vault_meta (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
"""


def db() -> sqlite3.Connection:
    if not getattr(_local, "conn", None):
        Cfg.ensure_dirs()
        conn = sqlite3.connect(Cfg.db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init():
    conn = db()
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate()
    if PROFILE.sealed:
        db().execute("UPDATE task_runs SET prompt_text='' WHERE prompt_text != ''")
        db().commit()
        for path in Cfg.runs_dir().glob("*/prompt.md"):
            path.unlink(missing_ok=True)


def _migrate():
    """轻量迁移：给已存在的表补新列（SQLite ALTER ADD COLUMN，幂等）"""
    for col, ddl in (
        ("error_class", "TEXT DEFAULT ''"),
        ("runner_env", "TEXT DEFAULT ''"),
        ("artifacts", "TEXT DEFAULT '[]'"),
        ("publication", "TEXT DEFAULT '{}'"),
    ):
        if col not in {r["name"] for r in q("PRAGMA table_info(task_runs)")}:
            db().execute(f"ALTER TABLE task_runs ADD COLUMN {col} {ddl}")
    if "default_branch" not in {r["name"] for r in q("PRAGMA table_info(projects)")}:
        db().execute("ALTER TABLE projects ADD COLUMN default_branch TEXT DEFAULT ''")
    if "shadow_repo" not in {r["name"] for r in q("PRAGMA table_info(projects)")}:
        db().execute("ALTER TABLE projects ADD COLUMN shadow_repo TEXT DEFAULT ''")
    if "last_synced_at" not in {r["name"] for r in q("PRAGMA table_info(projects)")}:
        db().execute("ALTER TABLE projects ADD COLUMN last_synced_at REAL DEFAULT 0")
    if "last_sync_error" not in {r["name"] for r in q("PRAGMA table_info(projects)")}:
        db().execute("ALTER TABLE projects ADD COLUMN last_sync_error TEXT DEFAULT ''")
    if "cwd" not in {r["name"] for r in q("PRAGMA table_info(task_defs)")}:
        db().execute("ALTER TABLE task_defs ADD COLUMN cwd TEXT DEFAULT ''")
    if "harness" not in {r["name"] for r in q("PRAGMA table_info(task_defs)")}:
        db().execute("ALTER TABLE task_defs ADD COLUMN harness TEXT DEFAULT ''")
    if "change_policy" not in {r["name"] for r in q("PRAGMA table_info(task_defs)")}:
        db().execute("ALTER TABLE task_defs ADD COLUMN change_policy TEXT DEFAULT 'always'")
    if "change_probes" not in {r["name"] for r in q("PRAGMA table_info(task_defs)")}:
        db().execute("ALTER TABLE task_defs ADD COLUMN change_probes TEXT DEFAULT '[]'")
    if "task_id" not in {r["name"] for r in q("PRAGMA table_info(task_runs)")}:
        db().execute("ALTER TABLE task_runs ADD COLUMN task_id INTEGER"
                     " REFERENCES task_defs(id) ON DELETE SET NULL")
    if "prompt_text" not in {r["name"] for r in q("PRAGMA table_info(task_runs)")}:
        db().execute("ALTER TABLE task_runs ADD COLUMN prompt_text TEXT DEFAULT ''")
    db().commit()


def q(sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple = ()) -> int:
    cur = db().execute(sql, args)
    db().commit()
    return cur.lastrowid


def close():
    """关闭当前线程连接；短生命周期 worker 退出前必须调用。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def audit(actor: str, action: str, target: str = "", detail: str = ""):
    execute("INSERT INTO audit_log(actor, action, target, detail, at) VALUES (?,?,?,?,?)",
            (actor, action, target, detail, time.time()))


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(text: str, default=None):
    try:
        return json.loads(text) if text else ({} if default is None else default)
    except (json.JSONDecodeError, TypeError):
        return {} if default is None else default
