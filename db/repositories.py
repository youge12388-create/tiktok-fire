"""run_records / run_items 仓储。"""

from __future__ import annotations

from .database import get_connection


def _row_to_record(row) -> dict:
    d = dict(row)
    d["risk_detected"] = bool(d.get("risk_detected"))
    return d


def create_run(
    account_id: str,
    task_type: str,
    status: str,
    started_at: str,
    finished_at: str | None,
    success_count: int,
    failed_count: int,
    risk_detected: bool,
    error: str | None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO run_records
                (account_id, task_type, started_at, finished_at, status,
                 success_count, failed_count, risk_detected, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                task_type,
                started_at,
                finished_at,
                status,
                success_count,
                failed_count,
                1 if risk_detected else 0,
                error,
            ),
        )
        return int(cur.lastrowid)


def update_run(
    run_id: int,
    *,
    status: str,
    finished_at: str | None,
    success_count: int,
    failed_count: int,
    risk_detected: bool,
    error: str | None,
) -> bool:
    """更新已创建的运行记录，返回记录是否存在。"""
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE run_records
            SET finished_at = ?, status = ?, success_count = ?, failed_count = ?,
                risk_detected = ?, error = ?
            WHERE id = ?
            """,
            (
                finished_at,
                status,
                success_count,
                failed_count,
                1 if risk_detected else 0,
                error,
                run_id,
            ),
        )
        return cur.rowcount > 0


def add_run_item(
    run_id: int,
    account_id: str,
    friend_name: str,
    status: str,
    message_type: str | None = None,
    message_preview: str | None = None,
    error: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO run_items
                (run_id, account_id, friend_name, message_type, message_preview,
                 status, error, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                account_id,
                friend_name,
                message_type,
                message_preview,
                status,
                error,
                started_at,
                finished_at,
            ),
        )
        return int(cur.lastrowid)


def _where_clause(account_id: str | None, status: str | None, date: str | None):
    clauses: list[str] = []
    params: list[object] = []
    if account_id:
        clauses.append("account_id = ?")
        params.append(account_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if date:
        clauses.append("started_at LIKE ?")
        params.append(f"{date}%")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def list_runs(
    account_id: str | None = None,
    status: str | None = None,
    date: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    where, params = _where_clause(account_id, status, date)
    sql = f"""
        SELECT * FROM run_records{where}
        ORDER BY started_at DESC, id DESC
        LIMIT ? OFFSET ?
    """
    with get_connection() as conn:
        rows = conn.execute(sql, [*params, limit, offset]).fetchall()
    return [_row_to_record(r) for r in rows]


def count_runs(
    account_id: str | None = None,
    status: str | None = None,
    date: str | None = None,
) -> int:
    where, params = _where_clause(account_id, status, date)
    sql = f"SELECT COUNT(*) AS n FROM run_records{where}"
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["n"]) if row else 0


def get_run(run_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM run_records WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        items = conn.execute(
            "SELECT * FROM run_items WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    rec = _row_to_record(row)
    rec["items"] = [dict(i) for i in items]
    return rec


def list_run_items(run_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM run_items WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def today_counts() -> dict:
    """今日各状态次数与成功率（基于 run_records）。"""
    date = _today_prefix()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS runs,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'uncertain' THEN 1 ELSE 0 END) AS uncertain,
                SUM(CASE WHEN risk_detected = 1 THEN 1 ELSE 0 END) AS risk,
                COALESCE(SUM(success_count), 0) AS sent_ok,
                COALESCE(SUM(failed_count), 0) AS sent_failed
            FROM run_records
            WHERE started_at LIKE ?
            """,
            (f"{date}%",),
        ).fetchone()
    return dict(row or {})


def _today_prefix() -> str:
    from datetime import datetime

    return datetime.now().astimezone().date().isoformat()
