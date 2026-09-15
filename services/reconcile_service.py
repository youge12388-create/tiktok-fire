"""续火核对：把「今天勾选的名单」与「今天的真实发送结果」对账。

数据来源：
- 名单：``core.ledger`` 中已勾选的联系人，``display_name`` 与 ``run_items.friend_name`` 同源；
- 结果：``run_items``（已完成运行的每联系人明细，排除 dry_run 干跑）。

作用：
- 判断整个勾选名单是否都续火成功，并明确指出失败的人与失败原因；
- 为「只对个别失败的人补发」提供精确名单，而不是重发整份名单。
"""

from __future__ import annotations

from datetime import datetime

from core import ledger
from db import repositories as run_repo

# run_items.status → 核对分组
_ITEM_TO_BUCKET = {
    "success": "succeeded",
    "failed": "failed",
    "uncertain": "uncertain",
    "skipped": "skipped",
}
BUCKETS = ("succeeded", "failed", "uncertain", "skipped", "pending")
# 自动/一键补发只处理「确定失败」；待确认可能已经送达，交给人工按需单独补发。
RETRY_BUCKETS = ("failed",)


def today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _bucket(raw: object) -> str:
    return _ITEM_TO_BUCKET.get(str(raw or ""), "pending")


def outcome_map(account_id: str | None = None, date: str | None = None) -> dict[str, dict]:
    """返回 ``{display_name: {status, reason, at}}``；只含当天有真实发送记录的人。"""
    outcomes: dict[str, dict] = {}
    for row in run_repo.contact_outcomes(account_id, date):
        name = str(row.get("friend_name") or "").strip()
        if not name:
            continue
        outcomes[name] = {
            "status": _bucket(row.get("status")),
            "reason": str(row.get("error") or ""),
            "at": str(row.get("finished_at") or row.get("started_at") or ""),
        }
    return outcomes


def report_from_entries(account_id: str, entries: list[dict], date: str | None = None) -> dict:
    """按已勾选名单生成核对报表；调用方已持有台账数据时使用，避免重复读盘。"""
    day = date or today()
    outcomes = outcome_map(account_id, day)
    counts = {bucket: 0 for bucket in BUCKETS}
    contacts: list[dict] = []
    for entry in entries:
        name = str(entry.get("display_name") or "").strip()
        if not name:
            continue
        found = outcomes.get(name)
        status = str((found or {}).get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
        contacts.append({
            "name": name,
            "status": status,
            "reason": str((found or {}).get("reason") or ""),
            "at": str((found or {}).get("at") or ""),
        })

    def _pick(*statuses: str) -> list[dict]:
        return [
            {"name": c["name"], "reason": c["reason"], "at": c["at"]}
            for c in contacts if c["status"] in statuses
        ]

    retry_names = [c["name"] for c in contacts if c["status"] in RETRY_BUCKETS]
    day_counts = run_repo.today_counts(account_id, day)
    return {
        "account_id": account_id,
        "date": day,
        "selected_total": len(contacts),
        "counts": counts,
        "need_retry": len(retry_names),
        "retry_names": retry_names,
        "retryable_names": [c["name"] for c in contacts if c["status"] != "succeeded"],
        "contacts": contacts,
        "failed": _pick("failed"),
        "uncertain": _pick("uncertain"),
        "skipped": _pick("skipped"),
        "pending": [c["name"] for c in contacts if c["status"] == "pending"],
        "risk_today": bool(day_counts.get("risk")),
        "running_today": bool(day_counts.get("running")),
        "last_run_at": run_repo.last_run_started_at(account_id, day),
    }


def account_report(account_id: str, date: str | None = None) -> dict:
    """读取该账号当前勾选名单并生成核对报表。"""
    return report_from_entries(account_id, ledger.get_selected(account_id), date)


def retry_candidates(account_id: str, date: str | None = None) -> list[str]:
    """默认补发名单：今日确定失败、且仍在勾选名单中的人。"""
    return list(account_report(account_id, date)["retry_names"])


def daily_overview(date: str | None = None) -> dict:
    """所有账号的当日核对总览，供总览页展示「谁没续上」。"""
    from . import account_service

    day = date or today()
    totals = {
        "selected": 0,
        "succeeded": 0,
        "failed": 0,
        "uncertain": 0,
        "skipped": 0,
        "pending": 0,
        "need_retry": 0,
        "risk_accounts": 0,
    }
    accounts: list[dict] = []
    for acc in account_service.list_accounts()["accounts"]:
        report = account_report(acc["id"], day)
        counts = report["counts"]
        accounts.append({
            "account_id": acc["id"],
            "name": acc.get("name") or acc["id"],
            "display_name": acc.get("display_name") or acc.get("name") or acc["id"],
            "enabled": bool(acc.get("enabled", True)),
            "running": bool(acc.get("running")),
            "session_status": acc.get("session_status") or "unknown",
            "state_file_exists": bool(acc.get("state_file_exists")),
            "selected_total": report["selected_total"],
            "counts": counts,
            "need_retry": report["need_retry"],
            "retry_names": report["retry_names"],
            "retryable_names": report["retryable_names"],
            "failed": report["failed"],
            "uncertain": report["uncertain"],
            "pending": report["pending"],
            "skipped": report["skipped"],
            "risk_today": report["risk_today"],
            "running_today": report["running_today"],
            "last_run_at": report["last_run_at"],
        })
        totals["selected"] += report["selected_total"]
        for bucket in ("succeeded", "failed", "uncertain", "skipped", "pending"):
            totals[bucket] += counts.get(bucket, 0)
        totals["need_retry"] += report["need_retry"]
        totals["risk_accounts"] += 1 if report["risk_today"] else 0
    return {"date": day, "accounts": accounts, "totals": totals}
