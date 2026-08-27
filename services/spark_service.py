"""续火任务配置与执行服务。"""

from __future__ import annotations

from core import scheduler
from core.config import DEFAULT_CONFIG, load_config, save_config

from .task_runtime import start_run


def get_task(account_id: str) -> dict:
    return load_config(account_id)


def put_task(account_id: str, config: dict) -> dict:
    unknown = [k for k in config if k not in DEFAULT_CONFIG]
    if unknown:
        raise ValueError("未知配置项：" + ", ".join(map(str, unknown)))
    merged = save_config(config, account_id)
    scheduler.apply_schedule(account_id)
    return merged


def dry_run(account_id: str) -> dict:
    start_run(account_id, dry=True)
    return {"started": True}


def run(account_id: str) -> dict:
    start_run(account_id, dry=False)
    return {"started": True}
