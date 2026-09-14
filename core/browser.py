"""共享的 Playwright 浏览器启动器。

统一集成：
- 反爬对抗参数与真实 Chrome 指纹；
- playwright_stealth 自动注入（若安装）；
- 中文环境（zh-CN）与 Asia/Shanghai 时区模拟；
- 全局并发信号量：最多 MAX_CONCURRENT_BROWSERS 个浏览器会话同时存在
  （参考「抖音自动续火花 2.1」的会话池并发上限，防多账号同时开太多浏览器触发风控）；
- 完善的生命周期管理与异常兜底。
"""

from __future__ import annotations

import logging
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from .accounts import acquire_browser_slot, release_browser_slot
from .config import account_browser_profile_path, get_valid_state_path
from .session_state import persist_context_state, read_storage_state

logger = logging.getLogger("douyin-cloud-streak")

_profile_locks_guard = threading.Lock()
_profile_locks: dict[str, threading.Lock] = {}
_PROFILE_STATE_MARKER = "state-source-mtime"


def _profile_lock(profile_path: Path) -> threading.Lock:
    key = str(profile_path.resolve())
    with _profile_locks_guard:
        return _profile_locks.setdefault(key, threading.Lock())

_COMMON_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
]


def refresh_authenticated_state(context, state_path: Path | str) -> bool:
    """保存页面加载期间刷新的 Cookie；失败只记录，不中断当前业务操作。"""
    try:
        saved = persist_context_state(context, state_path, require_login_cookie=True)
        if not saved:
            logger.warning("登录态刷新跳过：当前浏览器未检测到会话 Cookie")
        return saved
    except Exception as exc:  # noqa: BLE001
        logger.warning("登录态刷新保存失败（保留原文件）：%s", str(exc)[:200])
        return False


def _apply_stealth(page) -> None:
    """尝试注入 stealth 脚本规避常见浏览器自动化指纹检测。"""
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except Exception:
            pass


def _user_agent(browser) -> str:
    """让伪装 UA 的 Chrome 主版本与实际 Playwright 内核保持一致。"""
    major = str(getattr(browser, "version", "")).split(".", 1)[0] or "124"
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


def _user_agent_for_playwright(p) -> str:
    """Read the bundled Chromium major version before persistent launch.

    ``launch_persistent_context`` returns a context rather than a Browser
    handle, so the old post-launch version lookup is not available.  Probe
    once per browser launch to keep the existing version-aligned UA behavior.
    """
    probe = None
    try:
        probe = p.chromium.launch(headless=True, args=_COMMON_ARGS)
        return _user_agent(probe)
    except Exception:
        return _user_agent(None)
    finally:
        if probe:
            try:
                probe.close()
            except Exception:
                pass


def _restore_storage_state(
    context,
    state_file: str,
    profile_path: Path | None = None,
) -> bool:
    """Load a validated snapshot into a persistent or ephemeral context.

    ``launch_persistent_context`` does not accept the ``storage_state`` launch
    option.  New Playwright versions expose ``set_storage_state``; the small
    cookie/localStorage fallback keeps the project's older minimum version
    functional as well.
    """
    marker = profile_path / _PROFILE_STATE_MARKER if profile_path else None
    if marker:
        try:
            current_mtime = str(Path(state_file).stat().st_mtime_ns)
        except OSError:
            current_mtime = None
        if current_mtime is not None:
            try:
                if marker.read_text(encoding="ascii").strip() == current_mtime:
                    return False
            except (OSError, UnicodeError):
                pass
    else:
        current_mtime = None

    setter = getattr(context, "set_storage_state", None)
    if setter is not None:
        setter(state_file)
    else:
        state = read_storage_state(state_file)
        if not state:
            return False
        cookies = state.get("cookies") or []
        if cookies:
            context.add_cookies(cookies)
        for origin in state.get("origins") or []:
            origin_url = str(origin.get("origin") or "")
            entries = origin.get("localStorage") or []
            if not origin_url or not entries:
                continue
            payload = json.dumps(
                {"origin": origin_url, "entries": entries},
                ensure_ascii=False,
            )
            context.add_init_script(
                f"""
                (() => {{
                    const payload = {payload};
                    if (location.origin !== payload.origin) return;
                    for (const entry of payload.entries) {{
                        localStorage.setItem(entry.name, entry.value);
                    }}
                }})();
                """
            )

    if marker and current_mtime is not None:
        try:
            marker.write_text(current_mtime, encoding="ascii")
            if os.name == "posix":
                marker.chmod(0o600)
        except OSError:
            logger.warning("无法记录账号登录态快照版本：%s", marker)
    return True


@contextmanager
def open_browser(
    state_path: Path | str | None = None,
    headless: bool = True,
    account_id: str | None = None,
    **ctx_kwargs,
):
    """启动 Chromium 并返回 (playwright, browser, context, page)。

    用法::

        with open_browser() as (p, browser, context, page):
            page.goto(url)
            ...

    退出 with 块时自动关闭浏览器和 playwright。
    state_path 默认自愈寻找账号目录 data/state.json 或根目录 state.json（默认账号）。
    并发控制：进入时占用一个全局浏览器名额，超过上限会阻塞等待。
    """
    valid_state = Path(state_path) if state_path else get_valid_state_path(account_id)
    state_file = str(valid_state) if valid_state and valid_state.exists() else None
    profile_path = account_browser_profile_path(account_id)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            profile_path.chmod(0o700)
        except OSError:
            pass
    profile_guard = _profile_lock(profile_path)

    acquire_browser_slot()
    profile_guard.acquire()
    p = None
    browser = None
    context = None
    persistent = False
    try:
        p = sync_playwright().start()
        default_user_agent = _user_agent_for_playwright(p)
        defaults = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": default_user_agent,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "ignore_https_errors": True,
        }
        defaults.update(ctx_kwargs)

        # A persistent per-account profile keeps the browser identity and all
        # profile data stable across task and container restarts.  A changed
        # validated state snapshot is imported once, so fresh QR logins and
        # external restores are picked up without overwriting newer profile
        # cookies with an older snapshot after a transient disk failure.
        persistent = True
        try:
            context = p.chromium.launch_persistent_context(
                str(profile_path),
                headless=headless,
                args=_COMMON_ARGS,
                **defaults,
            )
            browser = context.browser
            if state_file:
                _restore_storage_state(context, state_file, profile_path)
            page = context.new_page()
        except Exception as exc:
            # A corrupt/incompatible profile must not prevent a task from
            # using the last validated state snapshot.  Keep the profile on
            # disk for diagnosis and fall back to an isolated context.
            logger.warning("账号浏览器档案不可用，回退到临时上下文：%s", str(exc)[:200])
            persistent = False
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            context = None
            browser = p.chromium.launch(headless=headless, args=_COMMON_ARGS)
            context = browser.new_context(**defaults)
            if state_file:
                _restore_storage_state(context, state_file)
            page = context.new_page()
        _apply_stealth(page)

        yield p, browser, context, page
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser and not persistent:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass
        profile_guard.release()
        release_browser_slot()
