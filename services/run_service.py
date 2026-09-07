"""运行结果持久化：写入 SQLite run_records/run_items，并保留 runtime.json 历史。"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core import runtime as core_runtime
from core.config import DATA_DIR
from db import repositories as run_repo

ARTIFACTS_DIR = DATA_DIR / "artifacts"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def artifact_path(account_id: str | None, started_at: str | None, run_id: int) -> Path:
    """返回某次运行的错误截图路径（仅当文件存在时可用）。"""
    date = (str(started_at or "")[:10]) or datetime.now().astimezone().date().isoformat()
    return ARTIFACTS_DIR / date / str(account_id) / str(run_id) / "error.png"


def _archive_screenshot(result: dict, account_id: str, run_id: int) -> None:
    """把暂存截图移到 run_id 目录，完成结构化归档。"""
    pending = result.get("screenshot")
    if not pending:
        return
    src = Path(pending)
    if not src.exists():
        return
    dst = artifact_path(account_id, result.get("at"), run_id)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except Exception:
        pass


def _derive_status(ok_n: int, failed_n: int, uncertain_n: int, risk: bool, stopped: bool = False) -> str:
    if stopped:
        return "uncertain"
    if risk or failed_n or (ok_n == 0 and uncertain_n == 0):
        return "failed"
    if uncertain_n:
        return "uncertain"
    return "success"


def record_run(result: dict, account_id: str, task_type: str = "spark") -> int:
    """把一次自动化运行结果落库，返回 run_id。"""
    core_runtime.record_run(result, account_id)  # 保留 runtime.json 兼容历史

    ok_n = len(result.get("ok", []))
    failed_n = len(result.get("failed", []))
    uncertain_n = len(result.get("uncertain", []))
    risk = bool(result.get("risk_detected") or result.get("rate_limited"))
    stopped = bool(result.get("stopped"))

    error = None
    for item in result.get("failed", []):
        if isinstance(item, dict) and item.get("name") == "_system":
            error = item.get("reason")
            break
    if stopped and error is None:
        error = "已手动停止"

    started_at = result.get("at") or _now()
    finished = _now()
    status = _derive_status(ok_n, failed_n, uncertain_n, risk, stopped)
    run_id = run_repo.create_run(
        account_id=account_id,
        task_type=task_type,
        status=status,
        started_at=started_at,
        finished_at=finished,
        success_count=ok_n,
        failed_count=failed_n,
        risk_detected=risk,
        error=error,
    )

    message = result.get("message") if isinstance(result.get("message"), str) else None
    for name in result.get("ok", []):
        run_repo.add_run_item(run_id, account_id, str(name), "success", message_preview=message)
    for item in result.get("failed", []):
        if isinstance(item, dict) and item.get("name") != "_system":
            run_repo.add_run_item(
                run_id, account_id, str(item["name"]), "failed",
                error=str(item.get("reason", "")), message_preview=message,
            )
    for item in result.get("uncertain", []):
        if isinstance(item, dict):
            run_repo.add_run_item(
                run_id, account_id, str(item.get("name", "")), "uncertain",
                error=str(item.get("reason", "")), message_preview=message,
            )
        else:
            run_repo.add_run_item(run_id, account_id, str(item), "uncertain", message_preview=message)
    _archive_screenshot(result, account_id, run_id)
    return run_id


def list_runs(account_id: str | None = None, status: str | None = None, date: str | None = None, limit: int = 200, offset: int = 0) -> dict:
    items = run_repo.list_runs(account_id, status, date, limit, offset)
    for it in items:
        it["artifact"] = artifact_path(it.get("account_id"), it.get("started_at"), it["id"]).exists()
    total = run_repo.count_runs(account_id, status, date)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_run(run_id: int) -> dict | None:
    rec = run_repo.get_run(run_id)
    if rec is not None:
        rec["artifact"] = artifact_path(rec.get("account_id"), rec.get("started_at"), rec["id"]).exists()
    return rec


def today_counts() -> dict:
    return run_repo.today_counts()
