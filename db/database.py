"""SQLite 连接与初始化（WAL 模式，进程内单库 data/app.db）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app_config import DATA_DIR

DB_PATH: Path = DATA_DIR / "app.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS run_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    risk_detected INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_account ON run_records(account_id);
CREATE INDEX IF NOT EXISTS idx_run_status ON run_records(status);
CREATE INDEX IF NOT EXISTS idx_run_started ON run_records(started_at);

CREATE TABLE IF NOT EXISTS run_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    account_id TEXT NOT NULL,
    friend_name TEXT NOT NULL,
    message_type TEXT,
    message_preview TEXT,
    status TEXT NOT NULL,
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(run_id) REFERENCES run_records(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_item_run ON run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_item_account ON run_items(account_id);
"""


def get_connection(timeout_seconds: float = 30) -> sqlite3.Connection:
    """每次调用返回一条新连接，避免跨线程共享 sqlite 连接的问题。"""
    timeout_ms = max(1, int(timeout_seconds * 1000))
    conn = sqlite3.connect(DB_PATH, timeout=timeout_seconds, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """确保数据库文件与表结构存在。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # journal_mode 会争用数据库锁，只在启动初始化时设置，普通请求不得重复切换。
        mode = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if mode != "wal":
            raise RuntimeError(f"SQLite WAL 模式初始化失败：{mode}")
        conn.executescript(SCHEMA_SQL)
        # 进程在任务中途重启时，避免历史记录永久停留在 running。
        conn.execute(
            """
            UPDATE run_records
            SET status = 'uncertain',
                finished_at = COALESCE(finished_at, ?),
                error = COALESCE(error, '服务重启时任务未完成')
            WHERE status = 'running'
            """,
            (datetime.now().astimezone().isoformat(timespec="seconds"),),
        )
