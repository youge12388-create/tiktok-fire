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


def _where_clause(account_id: str | None, status: str | None, date: str | None, risk: bool | None = None):
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
    if risk is not None:
        clauses.append("risk_detected = ?")
        params.append(1 if risk else 0)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def list_runs(
    account_id: str | None = None,
    status: str | None = None,
    date: str | None = None,
    limit: int = 200,
    offset: int = 0,
    risk: bool | None = None,
) -> list[dict]:
    where, params = _where_clause(account_id, status, date, risk)
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
    risk: bool | None = None,
) -> int:
    where, params = _where_clause(account_id, status, date, risk)
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


def today_counts(account_id: str | None = None, date: str | None = None) -> dict:
    """指定日期（默认今天）各状态次数与发送量统计（基于 run_records）。"""
    day = date or _today_prefix()
    clauses = ["started_at LIKE ?"]
    params: list[object] = [f"{day}%"]
    if account_id:
        clauses.append("account_id = ?")
        params.append(account_id)
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS runs,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status = 'uncertain' THEN 1 ELSE 0 END) AS uncertain,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN risk_detected = 1 THEN 1 ELSE 0 END) AS risk,
                COALESCE(SUM(success_count), 0) AS sent_ok,
                COALESCE(SUM(failed_count), 0) AS sent_failed
            FROM run_records
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchone()
    counts = dict(row or {})
    for key in ("runs", "ok", "failed", "uncertain", "running", "risk", "sent_ok", "sent_failed"):
        counts[key] = int(counts.get(key) or 0)
    return counts


def contact_outcomes(account_id: str | None = None, date: str | None = None) -> list[dict]:
    """指定日期每条联系人的最终发送结果（每个联系人只保留最后一次）。

    干跑记录不参与统计：dry_run 的 ok 明细只表示「文本可输入」，不代表真实送达，
    若计入会把测试运行误判成续火成功。
    """
    day = date or _today_prefix()
    clauses = ["r.started_at LIKE ?", "r.task_type != 'dry_run'", "i.friend_name != '_system'"]
    params: list[object] = [f"{day}%"]
    if account_id:
        clauses.append("i.account_id = ?")
        params.append(account_id)
    sql = f"""
        SELECT i.account_id, i.friend_name, i.status, i.error, i.message_preview,
               r.started_at, r.finished_at, i.id
        FROM run_items i
        JOIN run_records r ON r.id = i.run_id
        WHERE {" AND ".join(clauses)}
        ORDER BY i.id DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    latest: dict[tuple[str, str], dict] = {}
    for row in rows:
        item = dict(row)
        key = (item["account_id"], item["friend_name"])
        # 按 id 倒序遍历：先出现的即当天最后一次结果。
        if key not in latest:
            latest[key] = item
    return list(latest.values())


def last_run_started_at(account_id: str | None = None, date: str | None = None) -> str | None:
    """当天最近一次运行的开始时间（含干跑）。"""
    day = date or _today_prefix()
    clauses = ["started_at LIKE ?"]
    params: list[object] = [f"{day}%"]
    if account_id:
        clauses.append("account_id = ?")
        params.append(account_id)
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT started_at FROM run_records WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT 1",
            params,
        ).fetchone()
    return str(row["started_at"]) if row and row["started_at"] else None


def _today_prefix() -> str:
    from datetime import datetime

    return datetime.now().astimezone().date().isoformat()
