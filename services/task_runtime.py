"""账号级运行锁与后台任务线程，保证同一账号同时最多一个发送任务（§15）。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from core import scheduler
from core.runtime import load_runtime, set_running, update_runtime

from . import run_service
from .contact_service import sync_contacts
from .douyin import douyin
from .state import acquire_lock, contacts_fetching, harvesting, lock_for

logger = logging.getLogger("douyin-cloud-streak")


def start_run(account_id: str, dry: bool = False, only_names: list[str] | None = None) -> bool:
    """启动一次发送任务（dry=True 为干跑）。返回是否成功启动。"""
    if not acquire_lock(account_id):
        raise RuntimeError("该账号已有任务在运行，请稍后再试")
    threading.Thread(target=_run_worker, args=(account_id, dry, only_names), daemon=True).start()
    return True


def _run_worker(account_id: str, dry: bool, only_names: list[str] | None) -> None:
    try:
        set_running(True, account_id)
        try:
            result = douyin.run_spark(account_id, dry_run=dry, only_names=only_names)
            run_service.record_run(result, account_id, task_type="dry_run" if dry else "spark")
            if not dry and result.get("failed") and not result.get("logged_out"):
                _schedule_retry(account_id, result)
            elif not dry:
                scheduler.cancel_retry(account_id)
        finally:
            set_running(False, account_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 发送任务异常: %s", account_id, exc)
    finally:
        lock_for(account_id).release()


def _schedule_retry(account_id: str, result: dict) -> None:
    failed_names = [
        f["name"]
        for f in result.get("failed", [])
        if isinstance(f, dict) and isinstance(f.get("name"), str) and f["name"] != "_system"
    ]
    if not failed_names:
        return
    rt = load_runtime(account_id)
    today = datetime.now().date().isoformat()
    if rt.get("retry_date") != today:
        update_runtime(account_id, retry_date=today)
    scheduler.schedule_retry(lambda: _scheduled_run(account_id, failed_names), account_id=account_id)


def _scheduled_run(account_id: str, only_names: list[str] | None = None) -> None:
    """调度器回调包装：捕捉异常避免污染 scheduler。"""
    try:
        start_run(account_id, dry=False, only_names=only_names)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] 定时任务触发失败: %s", account_id, exc)


def start_fetch_contacts(account_id: str) -> bool:
    if not acquire_lock(account_id):
        raise RuntimeError("该账号已有任务在运行，请稍后再试")
    threading.Thread(target=_contacts_worker, args=(account_id,), daemon=True).start()
    return True


def _contacts_worker(account_id: str) -> None:
    try:
        contacts_fetching.add(account_id)
        try:
            sync_contacts(account_id)
        finally:
            contacts_fetching.discard(account_id)
    finally:
        lock_for(account_id).release()


def start_harvest_creator(account_id: str) -> bool:
    if account_id in harvesting:
        raise RuntimeError("creator 采集已在进行中")
    if lock_for(account_id).locked():
        raise RuntimeError("发送/同步任务进行中，请稍后再试")
    harvesting.add(account_id)
    threading.Thread(target=_harvest_worker, args=(account_id,), daemon=True).start()
    return True


def _harvest_worker(account_id: str) -> None:
    try:
        from core import ledger
        from core.runtime import record_harvest
        from core.harvester import creator_map

        res = creator_map.collect_short_id_map(account_id=account_id)
        merge_stats = None
        if res.get("mapping"):
            merge_stats = ledger.merge_creator_map(res["mapping"], account_id)
        harvest_last = {
            "at": res.get("at"),
            "count": res.get("count"),
            "hit": res.get("hit"),
            "error": res.get("error"),
            "merge": merge_stats,
        }
        record_harvest(harvest_last, account_id)
    finally:
        harvesting.discard(account_id)


def configured_run_cb() -> object:
    """供 scheduler.configure 使用的定时发送回调。"""
    return _scheduled_run
