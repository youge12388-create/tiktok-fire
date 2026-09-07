"""续火任务配置与执行服务。"""

from __future__ import annotations

from core import scheduler
from core.config import DEFAULT_CONFIG, load_config, save_config

from .task_runtime import request_stop, start_run


def get_task(account_id: str) -> dict:
    return load_config(account_id)


def put_task(account_id: str, config: dict) -> dict:
    unknown = [k for k in config if k not in DEFAULT_CONFIG]
    if unknown:
        raise ValueError("未知配置项：" + ", ".join(map(str, unknown)))
    merged = save_config(config, account_id)
    scheduler.apply_schedule(account_id)
    return merged


def set_auto_run(account_id: str, enabled: bool) -> dict:
    """切换该账号的自动运行开关，并刷新调度（关闭时移除每日定时任务）。"""
    merged = save_config({"auto_run_enabled": bool(enabled)}, account_id)
    scheduler.apply_schedule(account_id)
    return merged


def dry_run(account_id: str) -> dict:
    start_run(account_id, dry=True)
    return {"started": True}


def run(account_id: str) -> dict:
    start_run(account_id, dry=False)
    return {"started": True}


def stop(account_id: str) -> dict:
    """中断当前运行中的任务；无运行任务时返回 False。"""
    stopped = request_stop(account_id)
    return {"ok": True, "stopped": stopped}
