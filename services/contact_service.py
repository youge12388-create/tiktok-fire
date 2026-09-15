"""联系人同步与读取服务。"""

from __future__ import annotations

from core import ledger
from core.config import load_config, save_config
from core.runtime import load_runtime, update_runtime
from core.runtime import record_contacts as rt_record_contacts

from . import reconcile_service
from .douyin import douyin
from .notification_service import report_session_expired
from .state import contacts_fetching


def list_contacts(account_id: str) -> dict:
    """联系人列表：以好友台账为准（同步后的权威数据），附带勾选/会话/通道/今日结果。"""
    rt = load_runtime(account_id)
    outcomes = reconcile_service.outcome_map(account_id)
    contacts: list[dict] = []
    for e in ledger.load_ledger(account_id):
        streak = str(e.get("streak_days") or "") or ""
        name = e.get("display_name", "")
        outcome = outcomes.get(name) or {}
        contacts.append({
            "id": e.get("contact_key") or f"name:{name}",
            "name": name,
            "streak": streak,
            "avatar": e.get("avatar") or "",
            "selected": bool(e.get("selected")),
            "has_conversation": bool(e.get("has_conversation")),
            "channel": e.get("channel") or "none",
            "identity_ambiguous": bool(e.get("identity_ambiguous")),
            "today_status": outcome.get("status"),
            "today_reason": outcome.get("reason") or "",
            "today_at": outcome.get("at") or "",
        })
    selected = [c for c in contacts if c["selected"]]
    today_counts = {
        "succeeded": sum(1 for c in selected if c["today_status"] == "succeeded"),
        "failed": sum(1 for c in selected if c["today_status"] == "failed"),
        "uncertain": sum(1 for c in selected if c["today_status"] == "uncertain"),
        "skipped": sum(1 for c in selected if c["today_status"] == "skipped"),
        "pending": sum(1 for c in selected if not c["today_status"]),
    }
    return {
        "contacts": contacts,
        "contacts_at": rt.get("contacts_at"),
        "contacts_error": rt.get("contacts_error"),
        "contacts_warning": rt.get("contacts_warning"),
        "contacts_complete": rt.get("contacts_complete"),
        "contacts_scan_rounds": rt.get("contacts_scan_rounds"),
        "contacts_stop_reason": rt.get("contacts_stop_reason"),
        "contacts_scan_mode": rt.get("contacts_scan_mode"),
        "fetching": account_id in contacts_fetching,
        "selected_count": len(selected),
        "today_counts": today_counts,
        "account_id": account_id,
    }


def _contact_sync_key(contact: dict) -> str:
    conversation_id = str(contact.get("conversation_id") or "").strip()
    if conversation_id:
        return f"conversation:{conversation_id}"
    sync_key = str(contact.get("sync_key") or "").strip()
    if sync_key:
        return f"sync:{sync_key}"
    return f"name:{str(contact.get('name') or '').strip()}"


def _merge_scan_snapshots(previous: list[dict] | None, current: list[dict] | None) -> list[dict]:
    """按联系人稳定键合并扫描快照，当前扫描的数据覆盖旧的火花天数。"""
    merged: list[dict] = []
    positions: dict[str, int] = {}
    for item in (previous or []):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        key = _contact_sync_key(item)
        if key in positions:
            merged[positions[key]] = item
        else:
            positions[key] = len(merged)
            merged.append(item)
    for item in (current or []):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        key = _contact_sync_key(item)
        if key in positions:
            merged[positions[key]] = item
        else:
            positions[key] = len(merged)
            merged.append(item)
    return merged


def _sync_contacts(account_id: str, mode: str = "initial") -> dict:
    if mode not in {"initial", "supplement"}:
        raise ValueError("联系人同步 mode 必须是 initial 或 supplement")
    previous = (load_runtime(account_id).get("contacts") or []) if mode == "supplement" else []
    supplement = mode == "supplement"
    data = douyin.fetch_contacts(account_id, supplement=True) if supplement else douyin.fetch_contacts(account_id)
    data = dict(data or {})
    data["scan_mode"] = mode
    data["names"] = _merge_scan_snapshots(previous, data.get("names"))
    rt_record_contacts(data, account_id)
    if data.get("logged_out"):
        report_session_expired(account_id, str(data.get("error") or "同步联系人时检测到登录态失效"))
    merge_stats = None
    if data.get("names"):
        merge_stats = ledger.merge_consumer_contacts(data["names"], account_id)
        _remove_blocked_names_from_config(account_id, merge_stats)
    return {"data": data, "merge": merge_stats, "mode": mode}


def sync_contacts(account_id: str, mode: str = "initial") -> dict:
    """执行初次或补充扫描；保留已有联系人并把本次结果合并进去。"""
    return _sync_contacts(account_id, mode=mode)


def _mirror_friends(account_id: str, names: list[str]) -> None:
    """把当前勾选名单镜像到 config.friends，保持 CLI / 兼容路径可见。"""
    save_config({"friends": list(names)}, account_id)


def _remove_blocked_names_from_config(account_id: str, stats: dict | None) -> None:
    """同步清理同名联系人产生的历史选择，避免删除台账后 config.friends 又把它们带回。"""
    blocked = {
        str(name).replace("\u00a0", " ").strip()
        for name in (stats or {}).get("duplicate_names", [])
        if str(name).replace("\u00a0", " ").strip()
    }
    if not blocked:
        return
    cfg = load_config(account_id)
    keep = [
        name for name in cfg.get("friends", [])
        if str(name).replace("\u00a0", " ").strip() not in blocked
    ]
    if keep != cfg.get("friends", []):
        save_config({"friends": keep}, account_id)


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


def set_selection(account_id: str, names: list[str], contact_keys: list[str] | None = None) -> dict:
    """写入勾选：以台账为唯一选择来源，并镜像到 config.friends。

    传入完整勾选名单；不在名单内的现有联系人一律取消勾选。
    返回 {"selected", "updated", "added"}。
    """
    ordered = _normalize_names(names)
    requested_keys = _normalize_names(contact_keys)
    desired = set(ordered)
    desired_keys = set(requested_keys)
    current = ledger.load_ledger(account_id)
    updates: list[dict] = []
    for e in current:
        nm = str(e.get("display_name", ""))
        key = str(e.get("contact_key") or f"name:{nm}")
        in_list = key in desired_keys if requested_keys else nm in desired
        updates.append({
            "display_name": nm,
            "selected": in_list,
            "selected_order": (requested_keys.index(key) if requested_keys else ordered.index(nm)) if in_list else None,
            "contact_key": key,
        })
    existing = {str(e.get("display_name", "")) for e in current}
    for i, n in enumerate(ordered):
        if n not in existing and not requested_keys:
            updates.append({"display_name": n, "selected": True, "selected_order": i})
            existing.add(n)
    stats = ledger.set_selected(updates, account_id)
    _mirror_friends(account_id, ordered)
    return {"selected": ordered, "updated": stats["updated"], "added": stats["added"]}


def delete_contacts(account_id: str, names: list[str], contact_keys: list[str] | None = None) -> dict:
    """删除联系人：移出台账，并同步从 config.friends 移除。"""
    stats = ledger.remove_contacts(names, account_id, contact_keys=contact_keys)
    remove = set(_normalize_names(names))
    cfg = load_config(account_id)
    keep = [n for n in cfg.get("friends", []) if str(n).strip() not in remove]
    save_config({"friends": keep}, account_id)
    return stats


def delete_all_contacts(account_id: str) -> dict:
    """删除该账号全部联系人，并清空兼容配置中的勾选名单。"""
    stats = ledger.remove_all_contacts(account_id)
    save_config({"friends": []}, account_id)
    # 删除后不可让下一次「初次同步」把旧的 runtime 快照重新带回台账；
    # 补充同步只有在用户明确点击继续时才读取已有快照。
    update_runtime(
        account_id,
        contacts=[],
        contacts_at=None,
        contacts_error=None,
        contacts_warning=None,
        contacts_complete=None,
        contacts_scan_rounds=0,
        contacts_stop_reason="",
        contacts_scan_mode="initial",
    )
    return stats
