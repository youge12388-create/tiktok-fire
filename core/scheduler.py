"""每天定时触发发送任务（按账号独立注册 job）。"""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .accounts import list_accounts
from .config import DEFAULT_ACCOUNT_ID, load_config
from .runtime import load_runtime

logger = logging.getLogger("douyin-cloud-streak")
TZ = "Asia/Shanghai"
DEFAULT_LOGIN_CHECK_MINUTES = 60


def _login_check_interval_minutes() -> int:
    """登录巡检间隔（分钟）。可用环境变量 LOGIN_CHECK_INTERVAL_MINUTES 调整。

    巡检每轮都会真实打开一次抖音页面，间隔过短会显著放大风控压力，
    默认放宽到 60 分钟。
    """
    raw = (os.getenv("LOGIN_CHECK_INTERVAL_MINUTES") or "").strip()
    if not raw:
        return DEFAULT_LOGIN_CHECK_MINUTES
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("LOGIN_CHECK_INTERVAL_MINUTES=%r 不是有效整数，使用默认 %s 分钟", raw, DEFAULT_LOGIN_CHECK_MINUTES)
        return DEFAULT_LOGIN_CHECK_MINUTES

_scheduler: BackgroundScheduler | None = None
_scheduler_ready = False
_run_func: Callable | None = None
_harvest_func: Callable | None = None
_login_check_func: Callable | None = None
_retry_func: Callable | None = None


def _job_id(account_id: str, kind: str) -> str:
    return f"{kind}_{account_id}"


def _remove_job(job_id: str) -> None:
    """安全移除任务：任务不存在时忽略，避免 JobLookupError 中断配置。"""
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(job_id)
    except JobLookupError:
        return
    except Exception:  # noqa: BLE001
        logger.exception("移除调度任务失败：%s", job_id)


def _account_enabled(account_id: str) -> bool:
    """实时读取账号注册状态；账号已删除时视为不可执行。"""
    return any(
        account["id"] == account_id and bool(account.get("enabled", True))
        for account in list_accounts()
    )


def _account_allows_auto_run(account_id: str) -> bool:
    return _account_enabled(account_id) and bool(load_config(account_id).get("auto_run_enabled", True))


def _log_job_error(event) -> None:
    """把 APScheduler 后台异常写入应用日志，避免只留在调度器内部。"""
    logger.error(
        "[%s] 调度任务执行异常: %s\n%s",
        getattr(event, "job_id", "unknown"),
        getattr(event, "exception", "unknown"),
        getattr(event, "traceback", ""),
    )


def _daily_job(account_id: str) -> None:
    if not _account_enabled(account_id):
        logger.info("[%s] 账号已删除或停用，本次定时任务跳过", account_id)
        return
    cfg = load_config(account_id)
    if not bool(cfg.get("auto_run_enabled", True)):
        logger.info("[%s] 自动运行已关闭（auto_run_enabled=false），本次定时任务跳过", account_id)
        return
    # 0 表示明确关闭随机延迟，不能被 `or 30` 误解释成默认值。
    raw_jitter = cfg.get("jitter_minutes", 30)
    jitter = max(0, int(raw_jitter if raw_jitter is not None else 30))
    if jitter:
        delay = random.uniform(0, jitter * 60)
        logger.info("[%s] 随机延迟 %.0f 秒后开始发送（抖动窗口 %s 分钟）", account_id, delay, jitter)
        time.sleep(delay)
    # 抖动期间账号可能被停用/删除，配置也可能关闭；执行前必须读取最新状态。
    if not _account_allows_auto_run(account_id):
        logger.info("[%s] 随机延迟后账号不可自动运行，本次定时任务跳过", account_id)
        return
    if _run_func:
        _run_func(account_id=account_id)


def _harvest_job(account_id: str) -> None:
    if _harvest_func and _account_enabled(account_id):
        _harvest_func(account_id=account_id)


def _login_check_job(account_id: str) -> None:
    if _login_check_func and _account_enabled(account_id):
        _login_check_func(account_id=account_id)


def configure(
    run_func: Callable,
    harvest_func: Callable | None = None,
    login_check_func: Callable | None = None,
    retry_func: Callable | None = None,
) -> None:
    """注册每日发送、登录巡检与（可选）周级 creator 采集任务。"""
    global _scheduler, _scheduler_ready, _run_func, _harvest_func, _login_check_func, _retry_func
    _run_func = run_func
    _harvest_func = harvest_func
    _login_check_func = login_check_func
    _retry_func = retry_func
    try:
        if _scheduler is None:
            _scheduler = BackgroundScheduler(timezone=TZ)
            _scheduler.add_listener(_log_job_error, EVENT_JOB_ERROR)
            _scheduler.start()
        apply_schedule()
    except Exception:
        # 启动或首次注册失败时，不能让 health/readiness 误报为可用。
        _scheduler_ready = False
        logger.exception("调度器配置失败")
        failed_scheduler = _scheduler
        _scheduler = None
        if failed_scheduler is not None:
            try:
                failed_scheduler.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                logger.exception("调度器配置失败后的清理异常")
        raise


def apply_schedule(account_id: str | None = None) -> None:
    """应用调度配置并维护 readiness 状态；失败时向调用方传播异常。"""
    global _scheduler_ready
    if _scheduler is None:
        _scheduler_ready = False
        return
    try:
        _apply_schedule(account_id)
    except Exception:
        _scheduler_ready = False
        logger.exception("应用调度配置失败%s", f"（账号 {account_id}）" if account_id else "")
        raise
    _scheduler_ready = bool(getattr(_scheduler, "running", False))


def _apply_schedule(account_id: str | None = None) -> None:
    """按账号应用/更新定时任务。account_id 为 None 时对全部账号执行。"""
    if _scheduler is None:
        return

    accounts = list_accounts()
    if account_id is not None:
        accounts = [a for a in accounts if a["id"] == account_id]
    if not accounts:
        if account_id is not None:
            for kind in ("daily_send", "weekly_harvest", "login_check", "retry"):
                _remove_job(_job_id(account_id, kind))
            logger.info("[%s] 账号不存在，关联调度任务已移除", account_id)
        return

    for acc in accounts:
        aid = acc["id"]
        if not acc.get("enabled", True):
            _remove_job(_job_id(aid, "daily_send"))
            _remove_job(_job_id(aid, "weekly_harvest"))
            _remove_job(_job_id(aid, "login_check"))
            _remove_job(_job_id(aid, "retry"))
            logger.info("[%s] 账号已停用，定时任务已移除", aid)
            continue

        cfg = load_config(aid)
        auto = bool(cfg.get("auto_run_enabled", True))
        if auto:
            hh, mm = cfg.get("schedule_time", "21:00").split(":")
            _scheduler.add_job(
                _daily_job,
                CronTrigger(hour=int(hh), minute=int(mm), timezone=TZ),
                args=[aid],
                id=_job_id(aid, "daily_send"),
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=3600,
            )
            logger.info("[%s] 定时任务已更新：每天 %s:%s (%s)", aid, hh, mm, TZ)
        else:
            _remove_job(_job_id(aid, "daily_send"))
            _remove_job(_job_id(aid, "retry"))
            logger.info("[%s] 自动运行已关闭，已移除每日定时任务", aid)

        if _login_check_func:
            _scheduler.add_job(
                _login_check_job,
                IntervalTrigger(minutes=_login_check_interval_minutes(), timezone=TZ),
                args=[aid],
                id=_job_id(aid, "login_check"),
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
            )
        else:
            _remove_job(_job_id(aid, "login_check"))

        # 服务重启后恢复尚未执行的补发；实际名单仍会在回调中重新核对。
        pending = load_runtime(aid).get("retry_pending") or {}
        if _retry_func and pending.get("date") == datetime.now().astimezone().date().isoformat():
            schedule_retry(lambda aid=aid: _retry_func(account_id=aid), delay_minutes=0, account_id=aid)

        # 周级 creator 抖音号采集（默认周一 03:00；off/空 = 关闭）
        day = str(cfg.get("schedule_harvest_day") or "off").strip().lower()
        if day in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"} and _harvest_func:
            _scheduler.add_job(
                _harvest_job,
                CronTrigger(day_of_week=day, hour=3, minute=0, timezone=TZ),
                args=[aid],
                id=_job_id(aid, "weekly_harvest"),
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=3600,
            )
            logger.info("[%s] 周级采集已更新：每周 %s 03:00 (%s)", aid, day, TZ)
        else:
            _remove_job(_job_id(aid, "weekly_harvest"))
            if day not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
                logger.info("[%s] 周级采集已关闭", aid)


def _next_run(job) -> str | None:
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def next_run_time(account_id: str | None = None) -> str | None:
    if _scheduler is None:
        return None
    if account_id is None:
        return next_run_time(DEFAULT_ACCOUNT_ID)
    return _next_run(_scheduler.get_job(_job_id(account_id, "daily_send")))


def next_harvest_time(account_id: str | None = None) -> str | None:
    if _scheduler is None:
        return None
    if account_id is None:
        return next_harvest_time(DEFAULT_ACCOUNT_ID)
    return _next_run(_scheduler.get_job(_job_id(account_id, "weekly_harvest")))


def schedule_retry(run_func: Callable, delay_minutes: int = 45, account_id: str | None = None) -> None:
    if _scheduler is None:
        return
    aid = account_id or DEFAULT_ACCOUNT_ID
    if not _account_allows_auto_run(aid):
        logger.info("[%s] 账号不可自动运行，不安排补发任务", aid)
        return
    job_id = _job_id(aid, "retry")
    if _scheduler.get_job(job_id):
        return
    run_at = datetime.now().astimezone() + timedelta(minutes=delay_minutes)
    _scheduler.add_job(
        _retry_job,
        DateTrigger(run_date=run_at, timezone=TZ),
        args=[aid, run_func],
        id=job_id,
        replace_existing=True,
    )
    logger.info("[%s] 已安排 %s 分钟后自动补发本次失败或漏执行的联系人", aid, delay_minutes)


def _retry_job(account_id: str, run_func: Callable) -> None:
    """补发执行前再次确认账号仍存在、启用且允许自动运行。"""
    if not _account_allows_auto_run(account_id):
        logger.info("[%s] 补发触发时账号不可自动运行，本次补发跳过", account_id)
        return
    run_func()


def cancel_retry(account_id: str | None = None) -> None:
    job_id = _job_id(account_id or DEFAULT_ACCOUNT_ID, "retry")
    if _scheduler and _scheduler.get_job(job_id):
        _remove_job(job_id)
        logger.info("[%s] 已取消待执行的补发任务", account_id or DEFAULT_ACCOUNT_ID)


def shutdown() -> None:
    global _scheduler, _scheduler_ready
    _scheduler_ready = False
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        finally:
            _scheduler = None


def is_running() -> bool:
    """返回调度器是否已启动，供 readiness 健康检查使用。"""
    return bool(_scheduler_ready and _scheduler and getattr(_scheduler, "running", False))
