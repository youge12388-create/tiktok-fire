"""联系人选择闭环：配置合并、删除、选择同步、自动运行开关与停止标记。"""

from __future__ import annotations

import pytest

from core import accounts, ledger
from core.config import load_config, save_config
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


def test_duplicate_display_names_are_marked_ambiguous_and_not_pending(fresh_account):
    ledger.merge_consumer_contacts(
        [{"name": "同名", "streak": "5"}, {"name": "同名", "streak": "6"}],
        fresh_account,
    )
    contact = ledger.load_ledger(fresh_account)[0]
    assert contact["identity_ambiguous"] is True

    contact_service.set_selection(fresh_account, ["同名"])
    from core import automation

    assert automation.compute_pending(account_id=fresh_account) == []


def test_distinct_conversation_ids_keep_same_name_as_separate_safe_records(fresh_account):
    ledger.merge_consumer_contacts(
        [
            {"name": "同名", "streak": "5", "conversation_id": "conversation-a"},
            {"name": "同名", "streak": "6", "conversation_id": "conversation-b"},
        ],
        fresh_account,
    )

    contacts = contact_service.list_contacts(fresh_account)["contacts"]
    assert {item["id"] for item in contacts} == {"conversation:conversation-a", "conversation:conversation-b"}
    assert all(item["identity_ambiguous"] for item in contacts)

    removed = contact_service.delete_contacts(fresh_account, [], ["conversation:conversation-a"])
    assert removed["removed"] == 1
    assert [item["id"] for item in contact_service.list_contacts(fresh_account)["contacts"]] == ["conversation:conversation-b"]


def test_same_name_fallback_fingerprints_are_not_silently_merged(fresh_account):
    ledger.merge_consumer_contacts(
        [
            {"name": "同名", "streak": "5", "sync_key": "fallback:同名|avatar:a"},
            {"name": "同名", "streak": "6", "sync_key": "fallback:同名|avatar:b"},
        ],
        fresh_account,
    )

    contacts = contact_service.list_contacts(fresh_account)["contacts"]
    assert len(contacts) == 2
    assert all(item["identity_ambiguous"] for item in contacts)


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
