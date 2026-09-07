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
    if risk or failed_n:
        return "failed"
    if uncertain_n:
        return "uncertain"
    # 没有可发送目标或目标全部被安全规则跳过时，任务本身已正常结束，
    # 不应被展示成“失败”。发送数量仍由 success_count/failed_count 体现。
    return "success"


def start_run(account_id: str, task_type: str = "spark") -> int:
    """先创建 running 记录，让后台任务从启动瞬间起可见。"""
    return run_repo.create_run(
        account_id=account_id,
        task_type=task_type,
        status="running",
        started_at=_now(),
        finished_at=None,
        success_count=0,
        failed_count=0,
        risk_detected=False,
        error=None,
    )


def _result_count(result: dict, key: str) -> int:
    value = result.get(key)
    return len(value) if isinstance(value, (list, tuple)) else 0


def mark_run_uncertain(run_id: int, result: dict | None = None, reason: str = "运行结果落库失败，结果状态未知") -> bool:
    """持久化异常时结束预创建记录，避免历史中永久残留 running。"""
    result = result if isinstance(result, dict) else {}
    return run_repo.update_run(
        run_id,
        status="uncertain",
        finished_at=_now(),
        success_count=_result_count(result, "ok"),
        failed_count=_result_count(result, "failed"),
        risk_detected=bool(result.get("risk_detected") or result.get("rate_limited")),
        error=reason[:500],
    )


def record_run(
    result: dict,
    account_id: str,
    task_type: str = "spark",
    run_id: int | None = None,
) -> int:
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
    if run_id is None:
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
    elif not run_repo.update_run(
        run_id,
        status=status,
        finished_at=finished,
        success_count=ok_n,
        failed_count=failed_n,
        risk_detected=risk,
        error=error,
    ):
        # 记录可能因人工清理或旧数据库异常消失；不要因此丢掉本次结果。
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
