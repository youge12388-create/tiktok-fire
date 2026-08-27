"""进程内共享状态：账号级运行锁与采集标记。"""

from __future__ import annotations

import threading

account_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
contacts_fetching: set[str] = set()
harvesting: set[str] = set()


def lock_for(account_id: str) -> threading.Lock:
    with _locks_guard:
        lock = account_locks.get(account_id)
        if lock is None:
            lock = threading.Lock()
            account_locks[account_id] = lock
        return lock


def is_busy(account_id: str) -> bool:
    return lock_for(account_id).locked() or account_id in harvesting


def acquire_lock(account_id: str) -> bool:
    if account_id in harvesting:
        raise RuntimeError("creator 采集进行中，请稍后再试")
    return lock_for(account_id).acquire(blocking=False)
