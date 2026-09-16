"""续火核对与按人补发：验证「谁失败了」可查、只补发失败的人、干跑不参与核对。"""

from __future__ import annotations

from datetime import datetime

import pytest

from core import ledger
from db import repositories as repo
from db.database import get_connection
from services import reconcile_service, spark_service

ACCOUNT = "reconcile-test"


@pytest.fixture(autouse=True)
def _isolated_account():
    """每个用例都在干净的账号数据上运行：清空台账与运行明细。"""
    ledger.remove_all_contacts(ACCOUNT)
    with get_connection() as conn:
        conn.execute("DELETE FROM run_items WHERE account_id = ?", (ACCOUNT,))
        conn.execute("DELETE FROM run_records WHERE account_id = ?", (ACCOUNT,))
    yield
    ledger.remove_all_contacts(ACCOUNT)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _seed_selection(names: list[str]) -> None:
    ledger.set_selected(
        [{"display_name": name, "selected": True, "selected_order": i} for i, name in enumerate(names)],
        ACCOUNT,
    )


def _add_run(ok: list[str], failed: list[tuple[str, str]], *, task_type: str = "spark") -> int:
    """写入一条已完成的运行记录及其明细。"""
    rid = repo.create_run(
        ACCOUNT, task_type, "failed" if failed else "success",
        _now(), _now(), len(ok), len(failed), False, None,
    )
    for name in ok:
        repo.add_run_item(rid, ACCOUNT, name, "success")
    for name, reason in failed:
        repo.add_run_item(rid, ACCOUNT, name, "failed", error=reason)
    return rid


def test_report_separates_success_failure_and_pending():
    _seed_selection(["甲", "乙", "丙"])
    _add_run(["甲"], [("乙", "找不到聊天输入框")])

    report = reconcile_service.account_report(ACCOUNT)

    assert report["selected_total"] == 3
    assert report["counts"]["succeeded"] == 1
    assert report["counts"]["failed"] == 1
    # 丙今天没有发送记录，应显示为「未执行」而不是成功。
    assert report["counts"]["pending"] == 1
    assert report["need_retry"] == 2
    assert report["retry_names"] == ["乙", "丙"]
    assert report["failed"][0]["name"] == "乙"
    assert "找不到聊天输入框" in report["failed"][0]["reason"]


def test_retry_only_targets_failed_contacts(monkeypatch):
    _seed_selection(["甲", "乙", "丙"])
    _add_run(["甲"], [("乙", "发送失败")])

    captured: dict = {}

    def fake_start_run(account_id, dry=False, only_names=None):
        captured.update(account_id=account_id, dry=dry, only_names=only_names)
        return True

    monkeypatch.setattr(spark_service, "start_run", fake_start_run)

    result = spark_service.retry(ACCOUNT)

    # 补发确定失败与漏执行的人，成功的「甲」不在名单里。
    assert captured["only_names"] == ["乙", "丙"]
    assert result["count"] == 2
    assert result["started"] is True


def test_retry_rejects_names_outside_selection(monkeypatch):
    _seed_selection(["甲"])
    monkeypatch.setattr(spark_service, "start_run", lambda *_a, **_k: True)

    try:
        spark_service.retry(ACCOUNT, ["已删除的人"])
    except ValueError as exc:
        assert "没有可补发" in str(exc)
    else:
        raise AssertionError("不在勾选名单中的联系人不应被补发")


def test_retry_requires_something_to_do(monkeypatch):
    _seed_selection(["甲"])
    _add_run(["甲"], [])
    monkeypatch.setattr(spark_service, "start_run", lambda *_a, **_k: True)

    try:
        spark_service.retry(ACCOUNT)
    except ValueError as exc:
        assert "没有可补发" in str(exc)
    else:
        raise AssertionError("没有失败联系人时不应启动任务")


def test_dry_run_records_do_not_count_as_success():
    _seed_selection(["甲"])
    # 干跑的 ok 明细只表示文本可输入，不能算作续火成功。
    _add_run(["甲"], [], task_type="dry_run")

    report = reconcile_service.account_report(ACCOUNT)

    assert report["counts"]["succeeded"] == 0
    assert report["counts"]["pending"] == 1


def test_latest_result_wins_when_contact_retried():
    _seed_selection(["甲"])
    _add_run([], [("甲", "第一次失败")])
    _add_run(["甲"], [])

    report = reconcile_service.account_report(ACCOUNT)

    # 同一天重试成功后，甲应显示为成功而不是仍然失败。
    assert report["counts"]["succeeded"] == 1
    assert report["counts"]["failed"] == 0
    assert report["need_retry"] == 0


def test_success_is_sticky_when_later_retry_is_skipped():
    _seed_selection(["甲"])
    _add_run(["甲"], [])
    rid = repo.create_run(ACCOUNT, "spark", "success", _now(), _now(), 0, 0, False, None)
    repo.add_run_item(rid, ACCOUNT, "甲", "skipped", error="补发时已无需发送")

    report = reconcile_service.account_report(ACCOUNT)

    assert report["counts"]["succeeded"] == 1
    assert report["counts"]["skipped"] == 0


def test_explicit_retry_does_not_resend_successful_contact(monkeypatch):
    _seed_selection(["甲"])
    _add_run(["甲"], [])
    monkeypatch.setattr(spark_service, "start_run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("不应启动补发")))

    with pytest.raises(ValueError, match="没有可补发"):
        spark_service.retry(ACCOUNT, ["甲"])


def test_skipped_contacts_are_persisted_and_reported(monkeypatch):
    _seed_selection(["甲"])
    monkeypatch.setattr(
        reconcile_service.run_repo,
        "contact_outcomes",
        lambda *_a, **_k: [{"friend_name": "甲", "status": "skipped", "error": "无会话且未开启「允许首条消息」", "started_at": _now(), "finished_at": _now()}],
    )

    report = reconcile_service.account_report(ACCOUNT)

    assert report["counts"]["skipped"] == 1
    assert report["counts"]["pending"] == 0
    assert report["skipped"][0]["name"] == "甲"


def test_record_run_persists_skipped_items():
    from services import run_service

    run_id = run_service.start_run(ACCOUNT)
    run_service.record_run(
        {
            "at": _now(),
            "ok": ["甲"],
            "failed": [],
            "skipped": [{"name": "乙", "reason": "无会话且未开启「允许首条消息」"}],
            "uncertain": [],
            "risk_detected": False,
            "rate_limited": False,
            "stopped": False,
        },
        ACCOUNT,
        run_id=run_id,
    )

    items = {item["friend_name"]: item for item in repo.get_run(run_id)["items"]}
    assert items["乙"]["status"] == "skipped"
    assert "允许首条消息" in items["乙"]["error"]
