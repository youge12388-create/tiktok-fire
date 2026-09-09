from db import repositories as repo


def test_create_and_query_run():
    rid = repo.create_run(
        "default", "spark", "success",
        "2026-08-27T10:00:00+08:00", "2026-08-27T10:01:00+08:00",
        2, 0, False, None,
    )
    repo.add_run_item(rid, "default", "甲", "success")
    repo.add_run_item(rid, "default", "乙", "failed", error="没发出去")
    detail = repo.get_run(rid)
    assert detail is not None
    assert len(detail["items"]) == 2
    assert any(r["id"] == rid for r in repo.list_runs(status="success"))
    assert not any(r["id"] == rid for r in repo.list_runs(status="failed"))


def test_filter_by_account_and_date():
    rid = repo.create_run("acc_1", "spark", "failed", "2026-08-27T11:00:00+08:00", "2026-08-27T11:00:05+08:00", 0, 1, True, "限流")
    assert any(r["id"] == rid for r in repo.list_runs(account_id="acc_1", date="2026-08-27"))
    assert repo.get_run(rid)["risk_detected"] is True


def test_wal_mode_enabled():
    from db.database import get_connection

    with get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_read_connection_stays_available_during_write_transaction():
    from db.database import get_connection

    with get_connection() as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            """
            INSERT INTO run_records
                (account_id, task_type, status, success_count, failed_count, risk_detected)
            VALUES ('health-lock-test', 'dry_run', 'running', 0, 0, 0)
            """
        )
        with get_connection() as reader:
            row = reader.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        writer.rollback()

    assert row[0] > 0
