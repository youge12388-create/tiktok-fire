"""联系人同步与读取服务。"""

from __future__ import annotations

from core import ledger
from core.runtime import load_runtime
from core.runtime import record_contacts as rt_record_contacts

from .douyin import douyin
from .state import contacts_fetching


def list_contacts(account_id: str) -> dict:
    rt = load_runtime(account_id)
    return {
        "contacts": rt.get("contacts", []),
        "contacts_at": rt.get("contacts_at"),
        "contacts_error": rt.get("contacts_error"),
        "fetching": account_id in contacts_fetching,
        "account_id": account_id,
    }


def sync_contacts(account_id: str) -> dict:
    """同步联系人：抓取 -> 写 runtime -> 合并进好友台账。"""
    data = douyin.fetch_contacts(account_id)
    rt_record_contacts(data, account_id)
    merge_stats = None
    if data.get("names"):
        merge_stats = ledger.merge_consumer_contacts(data["names"], account_id)
    return {"data": data, "merge": merge_stats}
