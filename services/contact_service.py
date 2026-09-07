"""联系人同步与读取服务。"""

from __future__ import annotations

from core import ledger
from core.config import load_config, save_config
from core.runtime import load_runtime
from core.runtime import record_contacts as rt_record_contacts

from .douyin import douyin
from .state import contacts_fetching


def list_contacts(account_id: str) -> dict:
    """联系人列表：以好友台账为准（同步后的权威数据），附带勾选/会话/通道状态。"""
    rt = load_runtime(account_id)
    contacts: list[dict] = []
    for e in ledger.load_ledger(account_id):
        streak = str(e.get("streak_days") or "") or ""
        contacts.append({
            "name": e.get("display_name", ""),
            "streak": streak,
            "avatar": e.get("avatar") or "",
            "selected": bool(e.get("selected")),
            "has_conversation": bool(e.get("has_conversation")),
            "channel": e.get("channel") or "none",
            "identity_ambiguous": bool(e.get("identity_ambiguous")),
        })
    selected_count = sum(1 for c in contacts if c["selected"])
    return {
        "contacts": contacts,
        "contacts_at": rt.get("contacts_at"),
        "contacts_error": rt.get("contacts_error"),
        "fetching": account_id in contacts_fetching,
        "selected_count": selected_count,
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


def _mirror_friends(account_id: str, names: list[str]) -> None:
    """把当前勾选名单镜像到 config.friends，保持 CLI / 兼容路径可见。"""
    save_config({"friends": list(names)}, account_id)


def _normalize_names(names: list[str] | None) -> list[str]:
    """去空白、去重、保序的名单。"""
    seen: set[str] = set()
    out: list[str] = []
    for n in (names or []):
        n = str(n).strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def set_selection(account_id: str, names: list[str]) -> dict:
    """写入勾选：以台账为唯一选择来源，并镜像到 config.friends。

    传入完整勾选名单；不在名单内的现有联系人一律取消勾选。
    返回 {"selected", "updated", "added"}。
    """
    ordered = _normalize_names(names)
    desired = set(ordered)
    current = ledger.load_ledger(account_id)
    updates: list[dict] = []
    for e in current:
        nm = str(e.get("display_name", ""))
        in_list = nm in desired
        updates.append({
            "display_name": nm,
            "selected": in_list,
            "selected_order": ordered.index(nm) if in_list else None,
        })
    existing = {str(e.get("display_name", "")) for e in current}
    for i, n in enumerate(ordered):
        if n not in existing:
            updates.append({"display_name": n, "selected": True, "selected_order": i})
            existing.add(n)
    stats = ledger.set_selected(updates, account_id)
    _mirror_friends(account_id, ordered)
    return {"selected": ordered, "updated": stats["updated"], "added": stats["added"]}


def delete_contacts(account_id: str, names: list[str]) -> dict:
    """删除联系人：移出台账，并同步从 config.friends 移除。"""
    stats = ledger.remove_contacts(names, account_id)
    remove = set(_normalize_names(names))
    cfg = load_config(account_id)
    keep = [n for n in cfg.get("friends", []) if str(n).strip() not in remove]
    save_config({"friends": keep}, account_id)
    return stats
