"""调度与自动补发的生命周期安全回归测试。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from apscheduler.jobstores.base import JobLookupError

from core import scheduler
from services import task_runtime


class FakeScheduler:
    def __init__(self, job_ids: tuple[str, ...] = ()) -> None:
        self.jobs = {job_id: object() for job_id in job_ids}
        self.added: list[dict] = []

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def remove_job(self, job_id: str) -> None:
        if job_id not in self.jobs:
            raise JobLookupError(job_id)
        del self.jobs[job_id]

    def add_job(self, func, trigger, **kwargs) -> None:
        self.added.append({"func": func, "trigger": trigger, **kwargs})
        self.jobs[kwargs["id"]] = object()


@pytest.mark.parametrize(
    "unsafe_field,unsafe_value",
    [
        ("risk_detected", True),
        ("rate_limited", True),
        ("logged_out", True),
        ("stopped", True),
        ("uncertain", [{"name": "甲", "reason": "结果未知"}]),
    ],
)
def test_unsafe_result_never_schedules_retry(unsafe_field, unsafe_value):
    result = {"failed": [{"name": "甲", "reason": "失败"}], unsafe_field: unsafe_value}
    assert task_runtime._retry_allowed(result) is False


def test_only_deterministic_failure_allows_retry():
    result = {
        "failed": [{"name": "甲", "reason": "明确失败"}],
        "uncertain": [],
        "risk_detected": False,
        "rate_limited": False,
        "logged_out": False,
        "stopped": False,
    }
    assert task_runtime._retry_allowed(result) is True


def test_unexecuted_selected_contact_allows_retry(monkeypatch):
    monkeypatch.setattr("services.reconcile_service.retry_candidates", lambda *_a, **_k: ["甲"])
    result = {"failed": [], "uncertain": [], "risk_detected": False, "rate_limited": False, "logged_out": False, "stopped": False}

    assert task_runtime._retry_allowed(result, "acc_1") is True


def test_retry_is_limited_to_once_per_day(monkeypatch):
    scheduled: list[str] = []
    today = datetime.now().date().isoformat()
    monkeypatch.setattr(task_runtime, "load_runtime", lambda account_id: {"retry_date": today, "retry_attempts": task_runtime.MAX_AUTO_RETRY_ATTEMPTS})
    monkeypatch.setattr(
        task_runtime.scheduler,
        "schedule_retry",
        lambda run_func, account_id: scheduled.append(account_id),
    )

    task_runtime._schedule_retry("acc_1", {"failed": [{"name": "甲"}]})

    assert scheduled == []


def test_retry_persists_failed_and_unexecuted_names(monkeypatch):
    scheduled: list[tuple[str, object]] = []
    state: dict = {}
    monkeypatch.setattr(task_runtime, "load_runtime", lambda _account_id: dict(state))
    monkeypatch.setattr(task_runtime, "update_runtime", lambda _account_id, **fields: state.update(fields))
    monkeypatch.setattr(task_runtime.scheduler, "is_running", lambda: True)
    monkeypatch.setattr(task_runtime.scheduler, "schedule_retry", lambda run_func, account_id, **_kwargs: scheduled.append((account_id, run_func)))
    monkeypatch.setattr("services.reconcile_service.retry_candidates", lambda *_a, **_k: ["乙"])

    task_runtime._schedule_retry("acc_1", {"failed": [{"name": "甲"}]})

    assert state["retry_pending"]["names"] == ["甲", "乙"]
    assert [item[0] for item in scheduled] == ["acc_1"]


def test_retry_allows_second_attempt_with_longer_delay(monkeypatch):
    today = datetime.now().date().isoformat()
    state = {"retry_date": today, "retry_attempts": 1}
    scheduled: list[int] = []
    monkeypatch.setattr(task_runtime, "load_runtime", lambda _account_id: dict(state))
    monkeypatch.setattr(task_runtime, "update_runtime", lambda _account_id, **fields: state.update(fields))
    monkeypatch.setattr(task_runtime.scheduler, "is_running", lambda: True)
    monkeypatch.setattr(task_runtime.scheduler, "schedule_retry", lambda _run_func, delay_minutes, account_id: scheduled.append(delay_minutes))
    monkeypatch.setattr("services.reconcile_service.retry_candidates", lambda *_a, **_k: ["甲"])

    task_runtime._schedule_retry("acc_1", {"failed": [{"name": "甲"}]})

    assert state["retry_attempts"] == 2
    assert scheduled == [45]


@pytest.mark.parametrize("account_state", [[], [{"id": "acc_1", "enabled": False}]])
def test_deleted_or_disabled_account_cleans_all_jobs(monkeypatch, account_state):
    job_ids = tuple(scheduler._job_id("acc_1", kind) for kind in ("daily_send", "weekly_harvest", "retry"))
    fake = FakeScheduler(job_ids)
    monkeypatch.setattr(scheduler, "_scheduler", fake)
    monkeypatch.setattr(scheduler, "list_accounts", lambda: account_state)

    scheduler.apply_schedule("acc_1")

    assert fake.jobs == {}


def test_daily_job_rechecks_account_after_random_delay(monkeypatch):
    events: list[str] = []
    states = iter(
        [
            [{"id": "acc_1", "enabled": True}],
            [{"id": "acc_1", "enabled": False}],
        ]
    )
    monkeypatch.setattr(scheduler, "list_accounts", lambda: next(states))
    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda account_id: {"auto_run_enabled": True, "jitter_minutes": 1},
    )
    monkeypatch.setattr(scheduler.random, "uniform", lambda start, end: 1)
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: events.append("slept"))
    monkeypatch.setattr(scheduler, "_run_func", lambda **kwargs: events.append("ran"))

    scheduler._daily_job("acc_1")

    assert events == ["slept"]


def test_zero_jitter_does_not_sleep(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(scheduler, "list_accounts", lambda: [{"id": "acc_1", "enabled": True}])
    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda account_id: {"auto_run_enabled": True, "jitter_minutes": 0},
    )
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: events.append("slept"))
    monkeypatch.setattr(scheduler, "_run_func", lambda **kwargs: events.append("ran"))

    scheduler._daily_job("acc_1")

    assert events == ["ran"]


def test_retry_job_rechecks_account_before_running(monkeypatch):
    ran: list[bool] = []
    monkeypatch.setattr(scheduler, "list_accounts", lambda: [{"id": "acc_1", "enabled": False}])

    scheduler._retry_job("acc_1", lambda: ran.append(True))

    assert ran == []


def test_unexpected_remove_error_is_logged(monkeypatch, caplog):
    class BrokenScheduler:
        def remove_job(self, job_id: str) -> None:
            raise RuntimeError("job store unavailable")

    monkeypatch.setattr(scheduler, "_scheduler", BrokenScheduler())

    with caplog.at_level("ERROR", logger="douyin-cloud-streak"):
        scheduler._remove_job("daily_send_acc_1")

    assert "移除调度任务失败" in caplog.text


def test_scheduler_error_listener_logs_background_exception(caplog):
    event = SimpleNamespace(job_id="daily_send_acc_1", exception=RuntimeError("boom"), traceback="trace")

    with caplog.at_level("ERROR", logger="douyin-cloud-streak"):
        scheduler._log_job_error(event)

    assert "daily_send_acc_1" in caplog.text
    assert "boom" in caplog.text


def test_configure_failure_clears_scheduler_readiness(monkeypatch):
    class BrokenScheduler:
        running = False

        def __init__(self, **_kwargs):
            pass

        def add_listener(self, *_args):
            pass

        def start(self):
            raise RuntimeError("scheduler unavailable")

        def shutdown(self, wait=False):
            pass

    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler, "_scheduler_ready", False)
    monkeypatch.setattr(scheduler, "BackgroundScheduler", BrokenScheduler)

    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        scheduler.configure(lambda **_kwargs: None)

    assert scheduler._scheduler is None
    assert scheduler.is_running() is False


def test_apply_schedule_failure_clears_scheduler_readiness(monkeypatch):
    class BrokenScheduler(FakeScheduler):
        running = True

        def add_job(self, *_args, **_kwargs):
            raise RuntimeError("job store unavailable")

    monkeypatch.setattr(scheduler, "_scheduler", BrokenScheduler())
    monkeypatch.setattr(scheduler, "_scheduler_ready", True)
    monkeypatch.setattr(scheduler, "list_accounts", lambda: [{"id": "acc_1", "enabled": True}])
    monkeypatch.setattr(
        scheduler,
        "load_config",
        lambda _account_id: {"auto_run_enabled": True, "schedule_time": "21:00"},
    )

    with pytest.raises(RuntimeError, match="job store unavailable"):
        scheduler.apply_schedule("acc_1")

    assert scheduler.is_running() is False
