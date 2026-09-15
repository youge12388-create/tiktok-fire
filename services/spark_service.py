"""续火任务配置与执行服务。"""

from __future__ import annotations

from core import ledger, scheduler
from core.config import DEFAULT_CONFIG, load_config, save_config

from . import reconcile_service
from .task_runtime import request_stop, start_run

_MAX_NAME_LENGTH = 200


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


def _dedupe_names(names: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in names or []:
        name = str(raw).strip()
        if not name:
            continue
        if len(name) > _MAX_NAME_LENGTH:
            raise ValueError(f"联系人名称过长：{name[:20]}…")
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def retry(account_id: str, names: list[str] | None = None, date: str | None = None) -> dict:
    """只补发指定联系人；不传 names 时补发「今日确定失败且仍在勾选名单中」的人。

    补发集合始终与当前勾选名单取交集——避免重发整份名单，也避免给已移除的人发送。
    不在名单中的请求会被明确回报（skipped），不静默忽略。
    """
    selected = {str(e.get("display_name") or "").strip() for e in ledger.get_selected(account_id)}
    requested = _dedupe_names(names) if names else reconcile_service.retry_candidates(account_id, date)
    targets = [name for name in requested if name in selected]
    skipped = [name for name in requested if name not in selected]
    if not targets:
        raise ValueError("没有可补发的联系人：今日没有确定失败的记录，或这些人已不在勾选名单中")
    start_run(account_id, dry=False, only_names=targets)
    return {"started": True, "count": len(targets), "names": targets, "skipped": skipped}


def reconcile(account_id: str, date: str | None = None) -> dict:
    return reconcile_service.account_report(account_id, date)


def stop(account_id: str) -> dict:
    """中断当前运行中的任务；无运行任务时返回 False。"""
    stopped = request_stop(account_id)
    return {"ok": True, "stopped": stopped}
