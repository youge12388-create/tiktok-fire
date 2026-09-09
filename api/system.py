"""健康检查与系统摘要。"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from core import scheduler
from db.database import get_connection
from services import account_service, notification_service, run_service

from .deps import require_admin

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger("douyin-cloud-streak")

_STARTED = time.time()
VERSION = "1.0.0"


@router.get("/health")
def health():
    db_ok = False
    try:
        # 健康检查必须快速失败，且实际读取 schema，不能只计算常量 SELECT 1。
        with get_connection(timeout_seconds=2) as conn:
            conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        db_ok = True
    except Exception:  # noqa: BLE001
        logger.exception("数据库健康检查失败")
        db_ok = False
    scheduler_ok = scheduler.is_running()
    ready = db_ok and scheduler_ok
    body = {
        "ok": ready,
        "ready": ready,
        "version": VERSION,
        "service": "douyin-cloud-streak",
        "checks": {"database": db_ok, "scheduler": scheduler_ok},
    }
    return JSONResponse(body, status_code=200 if ready else 503)


@router.get("/health/live")
def live_health():
    """仅表示进程可响应；容器编排应使用 /health 检查服务是否 ready。"""
    return {"ok": True, "version": VERSION, "service": "douyin-cloud-streak"}


@router.get("/notifications/status")
def notification_status(_admin: str = Depends(require_admin)):
    """只返回告警通道是否完整配置，绝不返回 Webhook 或密钥。"""
    return {"dingtalk": {"configured": notification_service.dingtalk_configured()}}


@router.post("/notifications/test")
def test_notification(_admin: str = Depends(require_admin)):
    ok, message = notification_service.send_test_notification()
    if not ok:
        status_code = 400 if not notification_service.dingtalk_configured() else 502
        raise HTTPException(status_code=status_code, detail=message)
    return {"ok": True, "message": message}


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
