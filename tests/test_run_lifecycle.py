from datetime import datetime

from db import init_db
from db import repositories as repo
from core import runtime
from services import run_service
from services import task_runtime


def test_running_record_is_finalized_with_same_id():
    run_id = run_service.start_run("default", task_type="spark")
    running = repo.get_run(run_id)
    assert running is not None
    assert running["status"] == "running"
    assert running["finished_at"] is None

    run_service.record_run(
        {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "ok": ["甲"],
            "failed": [],
            "uncertain": [],
            "risk_detected": False,
            "rate_limited": False,
            "stopped": False,
        },
        "default",
        run_id=run_id,
    )

    finished = repo.get_run(run_id)
    assert finished is not None
    assert finished["status"] == "success"
    assert finished["success_count"] == 1
    assert len(finished["items"]) == 1


def test_restart_marks_abandoned_running_records_uncertain():
    run_id = repo.create_run(
        "default",
        "spark",
        "running",
        "2026-09-07T10:00:00+08:00",
        None,
        0,
        0,
        False,
        None,
    )

    init_db()

    recovered = repo.get_run(run_id)
    assert recovered is not None
    assert recovered["status"] == "uncertain"
    assert recovered["finished_at"]
    assert recovered["error"] == "服务重启时任务未完成"


def test_restart_clears_stale_runtime_running_flag():
    runtime.update_runtime("default", running=True, stop_requested=True)

    assert runtime.recover_stale_running("default") is True
    recovered = runtime.load_runtime("default")
    assert recovered["running"] is False
    assert recovered["stop_requested"] is False


def test_disabled_account_cannot_start_task(monkeypatch):
    monkeypatch.setattr(task_runtime.accounts, "get_account", lambda account_id: {"id": account_id, "enabled": False})

    try:
        task_runtime.start_run("acc_disabled")
    except RuntimeError as exc:
        assert "已停用" in str(exc)
    else:
        raise AssertionError("disabled account unexpectedly started")


def test_result_persistence_failure_does_not_leave_running_record(monkeypatch):
    run_id = run_service.start_run("default", task_type="spark")
    result = {
        "ok": [],
        "failed": [{"name": "甲", "reason": "发送失败"}],
        "uncertain": [],
        "risk_detected": False,
        "rate_limited": False,
        "stopped": False,
    }
    monkeypatch.setattr(task_runtime.douyin, "run_spark", lambda *_args, **_kwargs: result)

    def fail_persist(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(task_runtime.run_service, "record_run", fail_persist)
    assert task_runtime.acquire_lock("default") is True

    task_runtime._run_worker("default", False, None, run_id)

    finished = repo.get_run(run_id)
    assert finished is not None
    assert finished["status"] == "uncertain"
    assert finished["finished_at"]
    assert "database unavailable" in (finished["error"] or "")
