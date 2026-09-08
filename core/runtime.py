"""运行状态与日志。运行结果持久化到账号目录 runtime.json，日志同时写文件与内存环形缓冲。"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from pathlib import Path
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR, account_dir, DEFAULT_ACCOUNT_ID

LOG_DIR = DATA_DIR / "logs"


def runtime_path(account_id: str | None = None) -> Path:
    return account_dir(account_id) / "runtime.json"


_lock = threading.Lock()
_ring: deque[str] = deque(maxlen=600)


def _default() -> dict:
    return {
        "session_status": "unknown",
        "running": False,
        "last_run": None,
        "history": [],
        "stop_requested": False,
    }


def load_runtime(account_id: str | None = None) -> dict:
    with _lock:
        return _load_unlocked(account_id)


def _load_unlocked(account_id: str | None = None) -> dict:
    """读取运行状态；调用方已持有 _lock 时使用。"""
    rt = _default()
    rp = runtime_path(account_id)
    if rp.exists():
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                rt.update(data)
        except Exception:
            pass
    return rt


def _write_unlocked(rt: dict, account_id: str | None = None) -> None:
    """原子写入运行状态；调用方已持有 _lock 时使用。"""
    d = account_dir(account_id)
    d.mkdir(parents=True, exist_ok=True)
    rp = runtime_path(account_id)
    tmp = rp.with_name(f"{rp.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(rt, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, rp)


def _save(rt: dict, account_id: str | None = None) -> None:
    with _lock:
        _write_unlocked(rt, account_id)


def _mutate(account_id: str | None, update) -> None:
    """在同一把锁内完成读改写，避免停止指令等并发更新互相覆盖。"""
    with _lock:
        rt = _load_unlocked(account_id)
        update(rt)
        _write_unlocked(rt, account_id)


def set_running(value: bool, account_id: str | None = None) -> None:
    _mutate(account_id, lambda rt: rt.update(running=bool(value)))


def set_stop_requested(account_id: str | None = None, value: bool = True) -> None:
    """请求中断当前运行中的任务：发送循环会在联系人之间检查该标记并提前退出。"""
    _mutate(account_id, lambda rt: rt.update(stop_requested=bool(value)))


def record_run(result: dict, account_id: str | None = None) -> None:
    def update(rt: dict) -> None:
        rt["last_run"] = result
        history = rt.get("history", [])
        if not isinstance(history, list):
            history = []
        history.insert(0, result)
        rt["history"] = history[:30]

        if result.get("logged_out"):
            rt["session_status"] = "expired"
        elif result.get("ok") and not result.get("failed"):
            rt["session_status"] = "ok"
        elif result.get("ok"):
            rt["session_status"] = "partial"
        elif not result.get("failed"):
            rt["session_status"] = "ok"
        else:
            rt["session_status"] = "failed"

    _mutate(account_id, update)


def record_contacts(data: dict, account_id: str | None = None) -> None:
    def update(rt: dict) -> None:
        rt["contacts"] = data.get("names", [])
        rt["contacts_at"] = data.get("at")
        rt["contacts_error"] = data.get("error")
        rt["contacts_warning"] = data.get("warning")
        rt["contacts_complete"] = bool(data.get("complete"))
        rt["contacts_scan_rounds"] = int(data.get("scan_rounds") or 0)
        rt["contacts_stop_reason"] = data.get("stop_reason") or ""

    _mutate(account_id, update)


def update_runtime(account_id: str | None = None, **fields) -> None:
    _mutate(account_id, lambda rt: rt.update(fields))


def claim_login_expired_alert(account_id: str, reason: str) -> bool:
    """原子地领取一次登录失效告警，防止并发任务重复通知。"""
    claimed = False

    def update(rt: dict) -> None:
        nonlocal claimed
        alert = rt.get("login_expired_alert") or {}
        if alert.get("active"):
            return
        rt["login_expired_alert"] = {
            "active": True,
            "reason": str(reason)[:300],
        }
        claimed = True

    _mutate(account_id, update)
    return claimed


def finish_login_expired_alert(account_id: str, delivered: bool) -> None:
    """记录告警尝试结果；即使投递失败也保持 active，避免反复轰炸。"""
    def update(rt: dict) -> None:
        alert = rt.get("login_expired_alert") or {}
        if alert.get("active"):
            alert["delivered"] = bool(delivered)
            rt["login_expired_alert"] = alert

    _mutate(account_id, update)


def clear_login_expired_alert(account_id: str) -> None:
    """仅在确认账号恢复登录后解除告警状态，使下次掉线可再次通知。"""
    def update(rt: dict) -> None:
        rt.pop("login_expired_alert", None)

    _mutate(account_id, update)


def recover_stale_running(account_id: str | None = None) -> bool:
    """服务重启后清理旧进程留下的运行/停止标记，返回是否发生过修复。"""
    recovered = False

    def update(rt: dict) -> None:
        nonlocal recovered
        if rt.get("running") or rt.get("stop_requested"):
            rt["running"] = False
            rt["stop_requested"] = False
            recovered = True

    _mutate(account_id, update)
    return recovered


def record_harvest(harvest_last: dict | None, account_id: str | None = None) -> None:
    """持久化最近一次 creator 采集摘要，服务重启后不丢（台账数据本身持久化不受影响）。"""
    def update(rt: dict) -> None:
        if harvest_last is None:
            rt.pop("harvest_last", None)
        else:
            rt["harvest_last"] = harvest_last

    _mutate(account_id, update)


def load_harvest_last(account_id: str | None = None) -> dict | None:
    """读取持久化的采集摘要；无记录返回 None。"""
    return load_runtime(account_id).get("harvest_last")


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _ring.append(self.format(record))
        except Exception:
            pass


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("douyin-cloud-streak")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # 长期运行的服务不能让单个 app.log 无限增长；保留约 50MB 的滚动历史。
    fh = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    rh = RingHandler()
    rh.setFormatter(fmt)
    logger.addHandler(rh)
    return logger


def recent_logs(n: int = 300) -> list[str]:
    return list(_ring)[-n:]
