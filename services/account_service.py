"""账号管理服务：账号 CRUD + 状态汇总 + 调度刷新。"""

from __future__ import annotations

from core import accounts, ledger, scheduler
from core.config import DEFAULT_ACCOUNT_ID, get_valid_state_path, load_config
from core.runtime import load_runtime

from .douyin import douyin
from .state import contacts_fetching, harvesting, is_busy


def _summary(a: dict) -> dict:
    aid = a["id"]
    rt = load_runtime(aid)
    return {
        **a,
        "session_status": rt.get("session_status", "unknown"),
        "running": rt.get("running", False) or is_busy(aid),
        "last_run": rt.get("last_run"),
        "next_run": douyin.next_run_time(aid),
        "next_harvest": douyin.next_harvest_time(aid),
        "contacts_fetching": aid in contacts_fetching,
        "harvesting": aid in harvesting,
        "state_file_exists": get_valid_state_path(aid) is not None,
        "douyin_nickname": rt.get("douyin_nickname") or "",
        "display_name": rt.get("douyin_nickname") or a["name"],
        "login_checked_at": rt.get("login_checked_at"),
        "login_check_reason": rt.get("login_check_reason") or "",
        "auto_run_enabled": bool(load_config(aid).get("auto_run_enabled", True)),
        "selected_count": len(ledger.get_selected(aid)),
    }


def list_accounts() -> dict:
    accts = [_summary(a) for a in accounts.list_accounts()]
    return {
        "accounts": accts,
        "current": DEFAULT_ACCOUNT_ID,
        "max_concurrent": accounts.MAX_CONCURRENT_BROWSERS,
        "browser_slots_available": accounts.browser_slots_available(),
        "version": "1.0.0",
    }


def create_account(name: str = "", device: str = "") -> dict:
    acc = accounts.create_account(name=name, device=device)
    scheduler.apply_schedule(acc["id"])
    return {"ok": True, "account": _summary(acc)}


def update_account(account_id: str, name: str | None = None, device: str | None = None, enabled: bool | None = None) -> dict | None:
    acc = accounts.update_account(account_id, name=name, device=device, enabled=enabled)
    if acc is None:
        return None
    scheduler.apply_schedule(account_id)
    return _summary(acc)


def delete_account(account_id: str) -> None:
    if account_id == DEFAULT_ACCOUNT_ID:
        raise RuntimeError("默认账号不允许删除")
    if is_busy(account_id):
        raise RuntimeError("该账号正在执行任务，请稍后再试")
    from core import login_session

    login_session.cancel(account_id)
    if not accounts.remove_account(account_id):
        raise KeyError(f"账号不存在：{account_id}")
    scheduler.apply_schedule(account_id)


def resolve(account_id: str | None) -> str:
    aid = (account_id or DEFAULT_ACCOUNT_ID).strip() or DEFAULT_ACCOUNT_ID
    if not accounts.account_exists(aid):
        raise KeyError(f"账号不存在：{aid}")
    return aid
