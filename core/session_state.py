"""抖音浏览器登录态的校验与安全持久化。"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path


LOGIN_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}

_locks_guard = threading.Lock()
_path_locks: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        return _path_locks.setdefault(key, threading.Lock())


def normalize_storage_state(state: object) -> dict:
    """校验 Playwright storage_state 的最小结构，拒绝写入残缺数据。"""
    if not isinstance(state, dict):
        raise ValueError("登录态必须是 JSON 对象")
    cookies = state.get("cookies", [])
    origins = state.get("origins", [])
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise ValueError("登录态 cookies/origins 结构无效")
    normalized = dict(state)
    normalized["cookies"] = cookies
    normalized["origins"] = origins
    return normalized


def has_login_cookie(state: dict) -> bool:
    """登录态中至少要有一个抖音会话 Cookie，才允许作为新状态落盘。"""
    return any(
        isinstance(cookie, dict)
        and (
            str(cookie.get("name") or "") in LOGIN_COOKIE_NAMES
            or str(cookie.get("name") or "").startswith("sessionid")
        )
        and bool(cookie.get("value"))
        for cookie in state.get("cookies", [])
    )


def read_storage_state(path: Path | str, *, require_login_cookie: bool = False) -> dict | None:
    """读取并校验登录态；文件缺失、JSON 损坏或结构无效时返回 None。"""
    target = Path(path)
    try:
        state = normalize_storage_state(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if require_login_cookie and not has_login_cookie(state):
        return None
    return state


def write_storage_state(path: Path | str, state: object) -> None:
    """用同目录唯一临时文件原子替换目标，失败时保留旧登录态。"""
    target = Path(path)
    normalized = normalize_storage_state(state)
    payload = json.dumps(normalized, ensure_ascii=False)
    target.parent.mkdir(parents=True, exist_ok=True)

    # PID/线程 ID 在容器重建或多实例共享卷时可能重复，UUID 用于消除跨进程碰撞。
    tmp = target.with_name(
        f"{target.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    with _lock_for(target):
        try:
            with tmp.open("x", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            if os.name == "posix":
                try:
                    parent_fd = os.open(target.parent, os.O_RDONLY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                except OSError:
                    # 部分挂载卷不支持目录 fsync；文件本身仍已完成原子替换。
                    pass
        finally:
            # replace 成功后临时文件已不存在；失败则清理本次唯一临时文件。
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def persist_context_state(
    context,
    path: Path | str,
    *,
    require_login_cookie: bool = True,
) -> bool:
    """导出当前浏览器状态；没有有效会话 Cookie 时不覆盖已有文件。"""
    state = normalize_storage_state(context.storage_state())
    if require_login_cookie and not has_login_cookie(state):
        return False
    write_storage_state(path, state)
    return True


def persist_account_context(context, account_id: str) -> bool:
    """保存账号登录态；默认账号同时维护旧版根目录兼容副本。"""
    from .config import DEFAULT_ACCOUNT_ID, ROOT_STATE_PATH, account_state_path

    state = normalize_storage_state(context.storage_state())
    if not has_login_cookie(state):
        return False
    write_storage_state(account_state_path(account_id), state)
    if account_id == DEFAULT_ACCOUNT_ID:
        try:
            write_storage_state(ROOT_STATE_PATH, state)
        except OSError:
            # data/state.json 是运行时主副本，根目录仅用于旧版脚本兼容。
            pass
    return True
