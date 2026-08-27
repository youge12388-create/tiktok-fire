"""健康检查与系统摘要。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from services import account_service, run_service

from .deps import require_admin

router = APIRouter(prefix="/system", tags=["system"])

_STARTED = time.time()
VERSION = "1.0.0"


@router.get("/health")
def health():
    return {"ok": True, "version": VERSION, "service": "douyin-cloud-streak"}


@router.get("/summary")
def summary(_admin: str = Depends(require_admin)):
    accounts = account_service.list_accounts()
    items = accounts["accounts"]
    return {
        "version": VERSION,
        "uptime_seconds": int(time.time() - _STARTED),
        "today": run_service.today_counts(),
        "accounts": {
            "total": len(items),
            "enabled": sum(1 for a in items if a.get("enabled", True)),
            "running": sum(1 for a in items if a.get("running")),
            "expired": sum(1 for a in items if a.get("session_status") in {"expired", "failed"}),
            "disabled": sum(1 for a in items if not a.get("enabled", True)),
        },
        "browser_slots_available": accounts.get("browser_slots_available", 0),
        "max_concurrent": accounts.get("max_concurrent", 0),
    }
