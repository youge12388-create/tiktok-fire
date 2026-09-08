"""账号级运行锁与后台任务线程，保证同一账号同时最多一个发送任务（§15）。"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from core import accounts, scheduler
from core.runtime import load_runtime, set_running, update_runtime

from . import run_service
from .contact_service import sync_contacts
from .douyin import douyin
from .notification_service import report_session_expired
from .state import acquire_lock, contacts_fetching, harvesting, lock_for

logger = logging.getLogger("douyin-cloud-streak")
_harvest_guard = threading.Lock()


def _ensure_account_enabled(account_id: str) -> None:
    account = accounts.get_account(account_id)
    if account is None:
        raise RuntimeError("账号不存在，无法启动任务")
    if not bool(account.get("enabled", True)):
        raise RuntimeError("账号已停用，请先启用后再执行任务")


def start_run(account_id: str, dry: bool = False, only_names: list[str] | None = None) -> bool:
    """启动一次发送任务（dry=True 为干跑）。返回是否成功启动。"""
    _ensure_account_enabled(account_id)
    if not acquire_lock(account_id):
        raise RuntimeError("该账号已有任务在运行，请稍后再试")
    try:
        # 删除账号会检查同一把运行锁；拿锁后再次检查，避免检查与启动之间被删除。
        _ensure_account_enabled(account_id)
    except Exception:
        lock_for(account_id).release()
        raise
    task_type = "dry_run" if dry else "spark"
    run_id: int | None = None
    try:
        # 在释放请求可见的账号锁之前先建立 running 记录，避免任务已开始但历史页无记录。
        run_id = run_service.start_run(account_id, task_type=task_type)
        update_runtime(account_id, running=True, stop_requested=False)
        threading.Thread(
            target=_run_worker,
            args=(account_id, dry, only_names, run_id),
            daemon=True,
        ).start()
        return True
    except Exception as exc:
        if run_id is not None:
            failure = _failure_result(account_id, dry, f"任务启动异常: {exc}")
            try:
                run_service.record_run(
                    failure,
                    account_id,
                    task_type=task_type,
                    run_id=run_id,
                )
            except Exception as persist_exc:  # noqa: BLE001
                logger.exception("[%s] 任务启动失败结果落库失败", account_id)
                _finish_persistence_failure(account_id, run_id, failure, persist_exc)
            try:
                update_runtime(account_id, running=False, stop_requested=False)
            except Exception:  # noqa: BLE001
                logger.exception("[%s] 任务启动失败后的运行状态清理失败", account_id)
        lock_for(account_id).release()
        raise


def _failure_result(account_id: str, dry: bool, reason: str) -> dict:
    return {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dry_run": bool(dry),
        "ok": [],
        "failed": [{"name": "_system", "reason": reason}],
        "skipped": [],
        "uncertain": [],
        "logged_out": False,
        "rate_limited": False,
        "risk_detected": False,
        "screenshot": None,
        "stopped": False,
        "account_id": account_id,
    }


def _finish_persistence_failure(
    account_id: str,
    run_id: int | None,
    result: dict,
    exc: Exception,
) -> None:
    """结果落库失败时结束预创建记录，避免遗留 running。"""
    if run_id is None:
        return
    try:
        marked = run_service.mark_run_uncertain(
            run_id,
            result,
            reason=f"运行结果落库失败，结果状态未知: {str(exc)[:200]}",
        )
        if not marked:
            logger.error("[%s] 运行结果落库失败且预创建记录不存在（run_id=%s）", account_id, run_id)
    except Exception:  # noqa: BLE001
        logger.exception("[%s] 无法结束异常运行记录（run_id=%s）", account_id, run_id)


def _run_worker(
    account_id: str,
    dry: bool,
    only_names: list[str] | None,
    run_id: int | None = None,
) -> None:
    result: dict | None = None
    try:
        try:
            result = douyin.run_spark(account_id, dry_run=dry, only_names=only_names)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] 发送任务异常: %s", account_id, exc)
            result = _failure_result(account_id, dry, f"后台任务异常: {exc}")
        if not isinstance(result, dict):
            logger.error("[%s] 自动化返回了非字典结果：%r", account_id, result)
            result = _failure_result(account_id, dry, "后台任务返回结果格式异常")

        persisted = True
        try:
            run_service.record_run(result, account_id, task_type="dry_run" if dry else "spark", run_id=run_id)
            if result.get("logged_out"):
                report_session_expired(
                    account_id,
                    str(next((item.get("reason") for item in result.get("failed", []) if isinstance(item, dict) and item.get("name") == "_system"), "发送任务检测到登录态失效")),
                )
        except Exception as exc:  # noqa: BLE001
            persisted = False
            logger.exception("[%s] 运行结果落库失败（run_id=%s）", account_id, run_id)
            _finish_persistence_failure(account_id, run_id, result, exc)

        try:
            # 结果落库失败时无法确认本轮实际发送结果，禁止自动补发，避免重复触达。
            if not dry and persisted and _retry_allowed(result):
                _schedule_retry(account_id, result)
            elif not dry:
                scheduler.cancel_retry(account_id)
        except Exception:  # noqa: BLE001
            logger.exception("[%s] 自动补发调度处理失败", account_id)
    finally:
        try:
            set_running(False, account_id)
            update_runtime(account_id, stop_requested=False)
        except Exception:  # noqa: BLE001
            logger.exception("[%s] 清理运行状态失败", account_id)
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
    if rt.get("retry_date") == today:
        logger.info("[%s] 今日已安排过自动补发，不再重复安排", account_id)
        return
    update_runtime(account_id, retry_date=today)
    scheduler.schedule_retry(lambda: _scheduled_run(account_id, failed_names), account_id=account_id)


def _retry_allowed(result: dict) -> bool:
    """仅确定性的普通失败允许自动补发；安全或结果不确定时必须人工处理。"""
    unsafe = (
        result.get("risk_detected")
        or result.get("rate_limited")
        or result.get("logged_out")
        or result.get("stopped")
        or result.get("uncertain")
    )
    return bool(result.get("failed")) and not bool(unsafe)


def _scheduled_run(account_id: str, only_names: list[str] | None = None) -> None:
    """调度器回调包装：捕捉异常避免污染 scheduler。"""
    try:
        start_run(account_id, dry=False, only_names=only_names)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] 定时任务触发失败: %s", account_id, exc)


def start_fetch_contacts(account_id: str, mode: str = "initial") -> bool:
    if mode not in {"initial", "supplement"}:
        raise ValueError("联系人同步 mode 必须是 initial 或 supplement")
    _ensure_account_enabled(account_id)
    if not acquire_lock(account_id):
        raise RuntimeError("该账号已有任务在运行，请稍后再试")
    try:
        _ensure_account_enabled(account_id)
    except Exception:
        lock_for(account_id).release()
        raise
    try:
        threading.Thread(target=_contacts_worker, args=(account_id, mode), daemon=True).start()
        return True
    except Exception:
        lock_for(account_id).release()
        raise


def _contacts_worker(account_id: str, mode: str = "initial") -> None:
    try:
        contacts_fetching.add(account_id)
        try:
            sync_contacts(account_id, mode=mode)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] 联系人同步异常: %s", account_id, exc)
            try:
                update_runtime(
                    account_id,
                    contacts_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                    contacts_error=f"联系人同步异常: {exc}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("[%s] 联系人同步错误状态保存失败", account_id)
        finally:
            contacts_fetching.discard(account_id)
    finally:
        lock_for(account_id).release()


def start_harvest_creator(account_id: str) -> bool:
    _ensure_account_enabled(account_id)
    with _harvest_guard:
        if account_id in harvesting:
            raise RuntimeError("creator 采集已在进行中")
        if not lock_for(account_id).acquire(blocking=False):
            raise RuntimeError("发送/同步任务进行中，请稍后再试")
        try:
            _ensure_account_enabled(account_id)
        except Exception:
            lock_for(account_id).release()
            raise
        harvesting.add(account_id)
    try:
        threading.Thread(target=_harvest_worker, args=(account_id,), daemon=True).start()
        return True
    except Exception:
        with _harvest_guard:
            harvesting.discard(account_id)
        lock_for(account_id).release()
        raise


def _harvest_worker(account_id: str) -> None:
    try:
        from core import ledger
        from core.runtime import record_harvest
        from core.harvester import creator_map

        try:
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
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] creator 采集或结果保存异常: %s", account_id, exc)
            try:
                record_harvest(
                    {
                        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "count": 0,
                        "hit": 0,
                        "error": f"creator 采集或结果保存异常: {exc}",
                        "merge": None,
                    },
                    account_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("[%s] creator 异常结果保存失败", account_id)
    finally:
        with _harvest_guard:
            harvesting.discard(account_id)
        lock_for(account_id).release()


def request_stop(account_id: str) -> bool:
    """请求中断当前运行中的任务；没有运行任务时返回 False。"""
    if not lock_for(account_id).locked():
        return False
    update_runtime(account_id, stop_requested=True)
    return True


def configured_run_cb() -> object:
    """供 scheduler.configure 使用的定时发送回调。"""
    return _scheduled_run
