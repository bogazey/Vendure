"""SQLite connection management and schema creation."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config.paths import DB_PATH

_local = threading.local()


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    platform TEXT NOT NULL,
    title TEXT,
    uploader TEXT,
    thumbnail TEXT,
    format_label TEXT,
    resolution TEXT,
    filepath TEXT,
    filesize INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    request_json TEXT,
    user_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at);
CREATE INDEX IF NOT EXISTS idx_history_platform ON history(platform);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
"""


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migrations for the raw sqlite3 layer (no Alembic
    here - this DB predates the commercial layer). `CREATE TABLE IF NOT
    EXISTS` doesn't add columns to an already-existing table, so a
    pre-commercial `data/app.db` needs `user_id` added by hand. The
    user_id index is created here too (never in the executescript'd SCHEMA
    above) so it never runs before this ALTER on an old database."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(history)").fetchall()}
    if "user_id" not in columns:
        conn.execute("ALTER TABLE history ADD COLUMN user_id TEXT")
        conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id)")
    conn.commit()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating the schema on first use."""
    path = db_path or DB_PATH
    key = str(path)
    conn = getattr(_local, "conn", None)
    conn_key = getattr(_local, "conn_key", None)
    if conn is not None and conn_key == key:
        return conn

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate_schema(conn)

    _local.conn = conn
    _local.conn_key = key
    return conn


@contextmanager
def get_cursor(db_path: Path | None = None) -> Iterator[sqlite3.Cursor]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def database_healthy(db_path: Path | None = None) -> bool:
    try:
        with get_cursor(db_path) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except sqlite3.Error:
        return False
