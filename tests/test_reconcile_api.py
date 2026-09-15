"""新接口的鉴权、参数校验与核对总览。"""

from __future__ import annotations

from datetime import datetime

import pytest

from core import accounts, ledger
from db import repositories as repo
from db.database import get_connection

PASSWORD = "T3st-Strong-Passw0rd!"


@pytest.fixture
def account_id():
    """新接口按账号解析 ID，必须注册真实账号才能通过 _resolve。"""
    acc = accounts.create_account(name="核对接口测试账号")
    yield acc["id"]
    accounts.remove_account(acc["id"])


@pytest.fixture(autouse=True)
def _clean_runs():
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM run_items WHERE account_id LIKE 'acc_%'")
        conn.execute("DELETE FROM run_records WHERE account_id LIKE 'acc_%'")


def _login(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _seed(account_id: str):
    ledger.set_selected(
        [{"display_name": "甲", "selected": True, "selected_order": 0},
         {"display_name": "乙", "selected": True, "selected_order": 1}],
        account_id,
    )
    rid = repo.create_run(account_id, "spark", "failed", _now(), _now(), 1, 1, False, None)
    repo.add_run_item(rid, account_id, "甲", "success")
    repo.add_run_item(rid, account_id, "乙", "failed", error="找不到聊天输入框")
    return rid


def test_reconcile_endpoints_require_login(client, account_id):
    assert client.get(f"/api/v1/accounts/{account_id}/spark-task/reconcile").status_code == 401
    assert client.post(f"/api/v1/accounts/{account_id}/spark-task/retry").status_code == 401
    assert client.get("/api/v1/system/reconcile/daily").status_code == 401


def test_reconcile_endpoint_reports_failed_contacts(client, account_id):
    _seed(account_id)
    _login(client)

    response = client.get(f"/api/v1/accounts/{account_id}/spark-task/reconcile")

    assert response.status_code == 200
    body = response.json()
    assert body["selected_total"] == 2
    assert body["retry_names"] == ["乙"]
    assert body["failed"][0]["name"] == "乙"


def test_daily_overview_includes_account_totals(client, account_id):
    _seed(account_id)
    _login(client)

    response = client.get("/api/v1/system/reconcile/daily")

    assert response.status_code == 200
    body = response.json()
    entry = next(a for a in body["accounts"] if a["account_id"] == account_id)
    assert entry["need_retry"] == 1
    assert body["totals"]["failed"] >= 1
    assert body["date"]


def test_invalid_date_is_rejected(client, account_id):
    _login(client)
    response = client.get(f"/api/v1/accounts/{account_id}/spark-task/reconcile", params={"date": "2026/01/01"})
    assert response.status_code == 422


def test_retry_endpoint_starts_only_named_contacts(client, account_id, monkeypatch):
    _seed(account_id)
    _login(client)
    captured: dict = {}

    def fake_start_run(target, dry=False, only_names=None):
        captured["only_names"] = only_names
        return True

    from services import spark_service

    monkeypatch.setattr(spark_service, "start_run", fake_start_run)

    response = client.post(f"/api/v1/accounts/{account_id}/spark-task/retry", json={"names": ["乙"]})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert captured["only_names"] == ["乙"]


def test_retry_endpoint_reports_nothing_to_retry(client, account_id):
    ledger.set_selected([{"display_name": "甲", "selected": True, "selected_order": 0}], account_id)
    _login(client)

    response = client.post(f"/api/v1/accounts/{account_id}/spark-task/retry", json={})

    assert response.status_code == 400
    assert "没有可补发" in response.json()["detail"]


def test_runs_endpoint_supports_risk_filter(client, account_id):
    _login(client)
    rid = repo.create_run(account_id, "spark", "failed", _now(), _now(), 0, 1, True, "限流")

    risky = client.get("/api/v1/runs", params={"account_id": account_id, "risk": "true"})
    safe = client.get("/api/v1/runs", params={"account_id": account_id, "risk": "false"})

    assert risky.status_code == 200
    assert any(item["id"] == rid for item in risky.json()["items"])
    assert not any(item["id"] == rid for item in safe.json()["items"])


def test_runs_endpoint_treats_empty_risk_as_no_filter(client, account_id):
    """前端清除筛选可能送出空串，应按不过滤处理而不是报错。"""
    _login(client)
    rid = repo.create_run(account_id, "spark", "failed", _now(), _now(), 0, 1, True, "限流")

    response = client.get("/api/v1/runs", params={"account_id": account_id, "risk": ""})

    assert response.status_code == 200
    assert any(item["id"] == rid for item in response.json()["items"])


def test_runs_endpoint_rejects_invalid_risk_value(client):
    _login(client)
    response = client.get("/api/v1/runs", params={"risk": "maybe"})
    assert response.status_code == 422


def test_contacts_endpoint_includes_today_status(client, account_id):
    _seed(account_id)
    _login(client)

    response = client.get(f"/api/v1/accounts/{account_id}/contacts")

    assert response.status_code == 200
    body = response.json()
    by_name = {c["name"]: c for c in body["contacts"]}
    assert by_name["甲"]["today_status"] == "succeeded"
    assert by_name["乙"]["today_status"] == "failed"
    assert "找不到聊天输入框" in by_name["乙"]["today_reason"]
    assert body["today_counts"]["succeeded"] == 1
    assert body["today_counts"]["failed"] == 1
