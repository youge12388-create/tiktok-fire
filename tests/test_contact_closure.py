"""联系人选择闭环：配置合并、删除、选择同步、自动运行开关与停止标记。"""

from __future__ import annotations

import pytest

from core import accounts, ledger
from core.config import load_config, save_config
from core.runtime import load_runtime
from services import contact_service

PWD = "T3st-Strong-Passw0rd!"


@pytest.fixture
def fresh_account():
    acc = accounts.create_account(name="闭环测试账号")
    yield acc["id"]
    accounts.remove_account(acc["id"])


def test_save_config_preserves_friends_on_partial_update(fresh_account):
    save_config({"friends": ["甲", "乙"], "schedule_time": "20:00"}, fresh_account)
    # 只更新时间，不应清空已选联系人
    save_config({"schedule_time": "21:30"}, fresh_account)
    cfg = load_config(fresh_account)
    assert cfg["friends"] == ["甲", "乙"]
    assert cfg["schedule_time"] == "21:30"


def test_remove_contacts_removes_entries(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "甲", "streak": "5"}, {"name": "乙", "streak": "6"}], fresh_account
    )
    stats = ledger.remove_contacts(["甲"], fresh_account)
    assert stats["removed"] == 1
    names = [e["display_name"] for e in ledger.load_ledger(fresh_account)]
    assert names == ["乙"]


def test_set_selection_syncs_ledger_and_config(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "甲", "streak": "5"}, {"name": "乙", "streak": "6"}, {"name": "丙", "streak": "1"}],
        fresh_account,
    )
    res = contact_service.set_selection(fresh_account, ["甲", "丙"])
    assert res["selected"] == ["甲", "丙"]
    selected = {e["display_name"] for e in ledger.get_selected(fresh_account)}
    assert selected == {"甲", "丙"}
    assert load_config(fresh_account)["friends"] == ["甲", "丙"]


def test_delete_contacts_removes_from_config(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "甲", "streak": "5"}, {"name": "乙", "streak": "6"}], fresh_account
    )
    contact_service.set_selection(fresh_account, ["甲", "乙"])
    res = contact_service.delete_contacts(fresh_account, ["甲"])
    assert res["removed"] == 1
    assert [e["display_name"] for e in ledger.load_ledger(fresh_account)] == ["乙"]
    assert load_config(fresh_account)["friends"] == ["乙"]


def test_delete_all_contacts_clears_ledger_config_and_runtime(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "甲", "streak": "5"}, {"name": "乙", "streak": "6"}], fresh_account
    )
    contact_service.set_selection(fresh_account, ["甲", "乙"])
    from core.runtime import update_runtime

    update_runtime(fresh_account, contacts=[{"name": "甲"}], contacts_complete=False)

    res = contact_service.delete_all_contacts(fresh_account)

    assert res == {"removed": 2, "total": 0}
    assert ledger.load_ledger(fresh_account) == []
    assert load_config(fresh_account)["friends"] == []
    runtime = load_runtime(fresh_account)
    assert runtime["contacts"] == []
    assert runtime["contacts_complete"] is None


def test_supplement_sync_merges_previous_partial_snapshot(fresh_account, monkeypatch):
    payloads = [
        {
            "names": [{"name": "甲", "streak": "5", "conversation_id": "conversation-a"}],
            "complete": False,
            "scan_rounds": 2,
            "stop_reason": "scroll_stalled",
        },
        {
            "names": [{"name": "乙", "streak": "7", "conversation_id": "conversation-b"}],
            "complete": True,
            "scan_rounds": 3,
            "stop_reason": "bottom_reached",
        },
    ]

    def fake_fetch(_account_id, supplement=False):
        data = dict(payloads.pop(0))
        data["scan_mode"] = "supplement" if supplement else "initial"
        return data

    monkeypatch.setattr(contact_service.douyin, "fetch_contacts", fake_fetch)

    first = contact_service.sync_contacts(fresh_account)
    second = contact_service.sync_contacts(fresh_account, mode="supplement")

    assert first["data"]["scan_mode"] == "initial"
    assert second["data"]["scan_mode"] == "supplement"
    assert {item["name"] for item in second["data"]["names"]} == {"甲", "乙"}
    assert {entry["display_name"] for entry in ledger.load_ledger(fresh_account)} == {"甲", "乙"}
    assert load_runtime(fresh_account)["contacts_complete"] is True


def test_duplicate_display_names_are_discarded_and_not_pending(fresh_account):
    stats = ledger.merge_consumer_contacts(
        [{"name": "同名", "streak": "5"}, {"name": "同名", "streak": "6"}],
        fresh_account,
    )
    assert stats["duplicate_names"] == ["同名"]
    assert ledger.load_ledger(fresh_account) == []

    contact_service.set_selection(fresh_account, ["同名"])
    from core import automation

    assert automation.compute_pending(account_id=fresh_account) == []


def test_distinct_conversation_ids_with_same_name_are_discarded_as_a_group(fresh_account):
    stats = ledger.merge_consumer_contacts(
        [
            {"name": "同名", "streak": "5", "conversation_id": "conversation-a"},
            {"name": "同名", "streak": "6", "conversation_id": "conversation-b"},
        ],
        fresh_account,
    )

    assert stats["duplicate_names"] == ["同名"]
    assert contact_service.list_contacts(fresh_account)["contacts"] == []


def test_same_name_fallback_fingerprints_are_discarded_as_a_group(fresh_account):
    stats = ledger.merge_consumer_contacts(
        [
            {"name": "同名", "streak": "5", "sync_key": "fallback:同名|avatar:a"},
            {"name": "同名", "streak": "6", "sync_key": "fallback:同名|avatar:b"},
        ],
        fresh_account,
    )

    assert stats["duplicate_names"] == ["同名"]
    assert contact_service.list_contacts(fresh_account)["contacts"] == []


def test_historical_duplicate_names_are_cleaned_on_next_scan(fresh_account, monkeypatch):
    # 模拟旧版本已落库的两个稳定会话；新同步不能继续展示同名待确认。
    ledger.set_selected(
        [
            {"display_name": "历史同名", "contact_key": "conversation:a", "selected": True},
            {"display_name": "历史同名", "contact_key": "conversation:b", "selected": True},
        ],
        fresh_account,
    )
    save_config({"friends": ["历史同名"]}, fresh_account)

    monkeypatch.setattr(
        contact_service.douyin,
        "fetch_contacts",
        lambda _account_id: {
            "names": [{"name": "新朋友", "streak": "3", "conversation_id": "conversation:new"}],
            "complete": True,
            "scan_rounds": 1,
            "stop_reason": "bottom_reached",
        },
    )
    result = contact_service.sync_contacts(fresh_account)
    stats = result["merge"]

    assert "历史同名" in stats["duplicate_names"]
    assert [e["display_name"] for e in ledger.load_ledger(fresh_account)] == ["新朋友"]
    assert load_config(fresh_account)["friends"] == []


def test_unique_legacy_name_entry_is_migrated_to_stable_contact_key(fresh_account):
    ledger.set_selected(
        [{"display_name": "待迁移", "contact_key": "name:待迁移", "selected": True, "selected_order": 0}],
        fresh_account,
    )

    stats = ledger.merge_consumer_contacts(
        [{"name": "待迁移", "streak": "8", "sync_key": "avatar:stable"}], fresh_account
    )

    contacts = contact_service.list_contacts(fresh_account)["contacts"]
    assert stats["migrated"] == 1
    assert len(contacts) == 1
    assert contacts[0]["id"] == "sync:avatar:stable"
    assert contacts[0]["selected"] is True
    assert contacts[0]["identity_ambiguous"] is False


def test_legacy_duplicate_is_removed_when_stable_contact_already_exists(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "待清理", "streak": "8", "sync_key": "avatar:stable"}], fresh_account
    )
    ledger.set_selected(
        [{"display_name": "待清理", "contact_key": "name:待清理", "selected": True, "selected_order": 0}],
        fresh_account,
    )

    stats = ledger.merge_consumer_contacts(
        [{"name": "待清理", "streak": "9", "sync_key": "avatar:stable"}], fresh_account
    )

    contacts = contact_service.list_contacts(fresh_account)["contacts"]
    assert stats["migrated"] == 1
    assert len(contacts) == 1
    assert contacts[0]["id"] == "sync:avatar:stable"
    assert contacts[0]["selected"] is True


def test_api_selection_delete_and_autorun(client):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": PWD})

    r = client.post("/api/v1/accounts", json={"name": "接口账号"})
    assert r.status_code == 200
    aid = r.json()["account"]["id"]

    try:
        base = f"/api/v1/accounts/{aid}"
        sel = client.put(f"{base}/contacts/selection", json={"names": ["张三", "李四"]})
        assert sel.status_code == 200 and sel.json()["selected"] == ["张三", "李四"]

        listing = client.get(f"{base}/contacts")
        assert listing.status_code == 200
        assert listing.json()["selected_count"] == 2
        checked = {c["name"] for c in listing.json()["contacts"] if c["selected"]}
        assert checked == {"张三", "李四"}

        # 自动运行开关：关闭后 daily job 移除，next_run 为空
        off = client.post(f"{base}/spark-task/auto-run", json={"enabled": False})
        assert off.status_code == 200 and off.json()["auto_run_enabled"] is False
        accounts_list = client.get("/api/v1/accounts").json()["accounts"]
        target = next(a for a in accounts_list if a["id"] == aid)
        assert target["auto_run_enabled"] is False
        assert target["next_run"] is None

        on = client.post(f"{base}/spark-task/auto-run", json={"enabled": True})
        assert on.status_code == 200 and on.json()["auto_run_enabled"] is True

        dlt = client.post(f"{base}/contacts/delete", json={"names": ["张三"]})
        assert dlt.status_code == 200 and dlt.json()["removed"] == 1
        listing = client.get(f"{base}/contacts")
        assert listing.json()["selected_count"] == 1
        checked = {c["name"] for c in listing.json()["contacts"] if c["selected"]}
        assert checked == {"李四"}
    finally:
        client.delete(f"/api/v1/accounts/{aid}")


def test_api_continue_sync_and_delete_all(client, monkeypatch):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": PWD})

    r = client.post("/api/v1/accounts", json={"name": "联系人动作接口账号"})
    assert r.status_code == 200
    aid = r.json()["account"]["id"]
    started = []

    def fake_start(account_id, mode="initial"):
        started.append((account_id, mode))
        return True

    monkeypatch.setattr("api.contacts.start_fetch_contacts", fake_start)
    try:
        sync = client.post(f"/api/v1/accounts/{aid}/contacts/sync/continue")
        assert sync.status_code == 200
        assert sync.json()["mode"] == "supplement"
        assert started == [(aid, "supplement")]

        ledger.merge_consumer_contacts(
            [{"name": "甲", "streak": "5"}, {"name": "乙", "streak": "6"}], aid
        )
        save_config({"friends": ["甲", "乙"]}, aid)
        deleted = client.post(f"/api/v1/accounts/{aid}/contacts/delete-all")
        assert deleted.status_code == 200
        assert deleted.json()["removed"] == 2
        assert client.get(f"/api/v1/accounts/{aid}/contacts").json()["contacts"] == []
    finally:
        client.delete(f"/api/v1/accounts/{aid}")
