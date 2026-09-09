"""网页端扫码登录会话管理（复刻「抖音自动续火花 2.1」的扫码机制）。

与 2.1 商业版 huohua.py 的流程一致，但基于 Playwright 实现且更简洁：

1. start(account_id)   为账号启动专属无头 Chromium（占用全局并发名额），
                       打开抖音并唤起登录二维码；
2. status(account_id)  前端轮询：返回当前状态与二维码 data URL；
3. 成功检测            轮询 cookie 出现 sessionid/sessionid_ss 即视为登录成功，
                       自动导出 storage_state 覆盖该账号 state.json 并销毁浏览器；
4. cancel(account_id)  手动取消；二维码过期自动点击刷新重新提取；
5. GC                  会话整体超时（默认 5 分钟）自动回收，防浏览器泄漏。

同账号同时只允许一个扫码会话；不同账号可各自扫码（受全局并发上限约束）。
"""

from __future__ import annotations

import base64
import logging
import os
import random
import shutil
import subprocess
import threading
import time
import uuid

from playwright.sync_api import sync_playwright

from .accounts import acquire_browser_slot, release_browser_slot
from .runtime import clear_login_expired_alert, update_runtime
from .session_state import LOGIN_COOKIE_NAMES, persist_account_context
from .selectors import (
    LOGIN_TAB_TEXT,
    QR_CLICK_CANDIDATES,
    QR_CODE_SELECTOR,
    QR_EXPIRED_TEXTS,
    QR_IMAGE_SELECTORS,
)

logger = logging.getLogger("douyin-cloud-streak")

CHAT_URL = "https://www.douyin.com/chat?isPopup=1"
PROFILE_URL = "https://www.douyin.com/user/self"

# 扫码等待总时长：覆盖"掏手机 -> 打开抖音 -> 扫码 -> 确认"的完整动作
SESSION_TIMEOUT = 300
# 二维码自动刷新次数上限（抖音二维码约 2~3 分钟过期一次）
QR_REFRESH_LIMIT = 5

# 登录成功判定 Cookie：覆盖抖音各端变体（sid_guard/sid_tt/uid_tt 与 sessionid 同批下发）
_LOGIN_COOKIE_NAMES = LOGIN_COOKIE_NAMES


_PROFILE_NICKNAME_JS = """
    () => {
        const selectors = [
            '[data-e2e="user-info"] h1', '[data-e2e="user-info"] [class*="nickname"]',
            '[class*="userInfo"] h1', '[class*="user-info"] h1',
            '[class*="profile"] h1', '[class*="nickname"]'
        ];
        for (const selector of selectors) {
            const value = document.querySelector(selector)?.textContent?.replace(/\\s+/g, ' ').trim();
            if (value && value.length <= 80) return value;
        }
        const title = (document.title || '').trim();
        const match = title.match(/^(.+?)(?:的主页|\\s*-\\s*抖音)/);
        return match?.[1]?.trim() || '';
    }
"""


def _extract_profile_nickname(page) -> str:
    """登录后读取本人主页昵称；页面结构变化时静默回退，不影响登录。"""
    try:
        page.goto(PROFILE_URL, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        nickname = str(page.evaluate(_PROFILE_NICKNAME_JS) or "").strip()
        return nickname[:80]
    except Exception as exc:
        logger.info("读取抖音账号昵称失败: %s", str(exc)[:100])
        return ""

_slot_guard = threading.Lock()
_slot_holders: set[tuple[str, str]] = set()
_ACTIVE_SESSION_STATUSES = {"queuing", "starting", "waiting_scan"}


def _acquire_slot_tracked(aid: str, session_id: str) -> None:
    """获取全局并发名额并登记归属，保证释放幂等（线程卡死被强制接管时不重复释放）。"""
    acquire_browser_slot()
    with _slot_guard:
        _slot_holders.add((aid, session_id))


def _release_slot_once(aid: str, session_id: str) -> None:
    with _slot_guard:
        key = (aid, session_id)
        if key not in _slot_holders:
            return
        _slot_holders.discard(key)
    release_browser_slot()


def _hard_expire(aid: str, session_id: str) -> None:
    """硬超时保护：工作线程卡死（如浏览器进程被杀后同步调用挂起）时强制终态。"""
    with _guard:
        st = _sessions.get(aid)
        if not st or st.get("session_id") != session_id:
            return
        flag = _stop_flags.get(aid)
        if flag:
            flag.set()
        if st["status"] in ("queuing", "starting", "waiting_scan"):
            st.update(status="expired", message="扫码会话超时，请重新发起扫码", qrcode="")
            logger.warning("[%s] 扫码会话触发硬超时保护（工作线程疑似卡死）", aid)
    _release_slot_once(aid, session_id)

_QR_SELECTORS = QR_IMAGE_SELECTORS

_QR_EXPIRED_TEXTS = QR_EXPIRED_TEXTS

_guard = threading.Lock()
_sessions: dict[str, dict] = {}
_stop_flags: dict[str, threading.Event] = {}


def _new_state(aid: str, **fields) -> dict:
    st = {
        "status": "starting",
        "message": "正在启动扫码环境…",
        "qrcode": "",
        "started_at": time.time(),
        "last_active": time.time(),
        "error": "",
    }
    st.update(fields)
    return st


def start(account_id: str) -> dict:
    """为指定账号启动扫码会话（幂等：已有活跃会话则直接返回其状态）。"""
    with _guard:
        old = _sessions.get(account_id)
        if old and old["status"] in ("queuing", "starting", "waiting_scan"):
            return {"ok": True, "resumed": True, **_public(old)}
        flag = threading.Event()
        session_id = uuid.uuid4().hex
        _stop_flags[account_id] = flag
        st = _new_state(
            account_id,
            session_id=session_id,
            status="queuing",
            message="正在排队获取浏览器名额…",
        )
        _sessions[account_id] = st

    t = threading.Thread(target=_session_worker, args=(account_id, flag, session_id), daemon=True)
    t.start()
    watchdog = threading.Timer(SESSION_TIMEOUT + 90, lambda: _hard_expire(account_id, session_id))
    watchdog.daemon = True
    watchdog.start()
    logger.info("[%s] 网页扫码会话已启动", account_id)
    return {"ok": True, "resumed": False, **_public(st)}


def status(account_id: str) -> dict:
    """查询会话状态（前端轮询入口）。无会话时返回 idle。"""
    with _guard:
        st = _sessions.get(account_id)
        if not st:
            return {"status": "idle", "message": "", "qrcode": ""}
        if st["status"] == "waiting_scan":
            st["last_active"] = time.time()
        return _public(st)


def cancel(account_id: str) -> dict:
    """取消/终止会话并释放浏览器。"""
    with _guard:
        st = _sessions.get(account_id)
        if not st or st["status"] in ("success", "failed", "expired", "cancelled"):
            _sessions.pop(account_id, None)
            _stop_flags.pop(account_id, None)
            return {"ok": True, "message": "无进行中的扫码会话"}
        session_id = st.get("session_id", "")
        flag = _stop_flags.get(account_id)
    if flag:
        flag.set()
    # 给线程一点时间自行清理，随后强制标记
    for _ in range(30):
        time.sleep(0.1)
        with _guard:
            cur = _sessions.get(account_id)
            if not cur or cur.get("session_id") != session_id:
                break
            if cur["status"] not in ("queuing", "starting", "waiting_scan"):
                break
    else:
        with _guard:
            cur = _sessions.get(account_id)
            if cur and cur.get("session_id") == session_id and cur["status"] in ("waiting_scan",):
                cur["status"] = "cancelled"
                cur["message"] = "已取消"
    logger.info("[%s] 扫码会话已取消", account_id)
    return {"ok": True, "message": "已取消"}


def _public(st: dict) -> dict:
    return {
        "status": st["status"],
        "message": st["message"],
        "qrcode": st["qrcode"] if st["status"] == "waiting_scan" else "",
        "error": st["error"],
    }


def _set(aid: str, session_id: str | None = None, **fields) -> None:
    with _guard:
        st = _sessions.get(aid)
        if st is None or (session_id is not None and st.get("session_id") != session_id):
            return
        st.update(fields)
        st["last_active"] = time.time()


def _is_stopped(aid: str, session_id: str | None = None) -> bool:
    with _guard:
        st = _sessions.get(aid)
        if session_id is not None and (st is None or st.get("session_id") != session_id):
            return True
        flag = _stop_flags.get(aid)
        return bool(flag and flag.is_set())


def _session_is_current(aid: str, session_id: str) -> bool:
    """判断会话仍是当前且未被取消；调用方不应据此跨锁执行副作用。"""
    with _guard:
        st = _sessions.get(aid)
        if not st or st.get("session_id") != session_id or st.get("status") not in _ACTIVE_SESSION_STATUSES:
            return False
        flag = _stop_flags.get(aid)
        return not (flag and flag.is_set())


def _save_state_if_current(context, aid: str, session_id: str) -> bool:
    """仅允许当前会话导出登录态，校验与写盘在同一把会话锁内完成。"""
    with _guard:
        st = _sessions.get(aid)
        flag = _stop_flags.get(aid)
        if (
            not st
            or st.get("session_id") != session_id
            or st.get("status") not in _ACTIVE_SESSION_STATUSES
            or (flag and flag.is_set())
        ):
            return False
        _save_state(context, aid)
        return True


def _update_nickname_if_current(aid: str, session_id: str, nickname: str) -> bool:
    """旧扫码线程退出或被替换后，不得覆盖新会话写入的昵称。"""
    with _guard:
        st = _sessions.get(aid)
        flag = _stop_flags.get(aid)
        if (
            not st
            or st.get("session_id") != session_id
            or st.get("status") not in _ACTIVE_SESSION_STATUSES
            or (flag and flag.is_set())
        ):
            return False
        fields = {"session_status": "ok"}
        if nickname:
            fields["douyin_nickname"] = nickname
        update_runtime(aid, **fields)
        clear_login_expired_alert(aid)
        return bool(nickname)


def _launch_browser(pw):
    """优先在 Xvfb 虚拟屏幕中启动有头 Chromium：真实有头内核的风控识别率远低于无头模式。

    返回 (browser, xvfb_proc)；Xvfb 不可用或启动失败时回退为无头模式。
    """
    common = dict(
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-software-rasterizer",
            # 小内存服务器 (2G) 防崩参数：限制渲染进程数、减少常驻进程
            "--renderer-process-limit=2",
            "--no-zygote",
            "--mute-audio",
        ],
        # 排除自动化开关，与商业版 excludeSwitches 等效
        ignore_default_args=["--enable-automation"],
    )
    if shutil.which("Xvfb"):
        for _ in range(4):
            display = f":{random.randint(90, 180)}"
            try:
                xproc = subprocess.Popen(
                    ["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(0.8)
                if xproc.poll() is not None:
                    continue  # 显示号被占用等，换一个重试
                try:
                    browser = pw.chromium.launch(
                        headless=False, env={**os.environ, "DISPLAY": display}, **common
                    )
                    return browser, xproc
                except Exception:
                    xproc.terminate()
            except Exception:
                continue
    return pw.chromium.launch(headless=True, **common), None


def _session_worker(aid: str, stop_flag: threading.Event, session_id: str) -> None:
    pw = None
    browser = None
    xvfb_proc = None
    try:
        queue_started = time.perf_counter()
        _acquire_slot_tracked(aid, session_id)
        logger.info(
            "[%s] 扫码浏览器名额已获取，排队耗时 %.2fs",
            aid,
            time.perf_counter() - queue_started,
        )
        if _is_stopped(aid, session_id):
            raise CancelledError()

        _set(aid, session_id, status="starting", message="正在打开抖音登录页…")
        browser_started = time.perf_counter()
        pw = sync_playwright().start()
        browser, xvfb_proc = _launch_browser(pw)
        logger.info(
            "[%s] 扫码浏览器启动完成，耗时 %.2fs",
            aid,
            time.perf_counter() - browser_started,
        )
        # UA 版本号与真实内核保持一致，固定旧版本号容易被风控识别为伪造环境
        chrome_major = (browser.version or "").split(".")[0] or "124"
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        # 与 2.1 商业版 stealth(webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine") 对齐
        context.add_init_script(
            "const _spoof=(proto)=>{const g=proto.getParameter;"
            "proto.getParameter=function(p){if(p===37445)return 'Intel Inc.';"
            "if(p===37446)return 'Intel Iris OpenGL Engine';return g.apply(this,[p]);};};"
            "if(window.WebGLRenderingContext)_spoof(WebGLRenderingContext.prototype);"
            "if(window.WebGL2RenderingContext)_spoof(WebGL2RenderingContext.prototype);"
        )
        page = context.new_page()
        try:
            from .browser import _apply_stealth
            _apply_stealth(page)
        except Exception:
            pass

        navigation_started = time.perf_counter()
        page.goto(CHAT_URL, timeout=60000, wait_until="domcontentloaded")
        logger.info(
            "[%s] 抖音登录页 DOM 已加载，耗时 %.2fs",
            aid,
            time.perf_counter() - navigation_started,
        )

        # 页面资源加载速度波动较大。等待登录标签可见即可继续，避免无条件多等 3 秒。
        try:
            page.get_by_text(LOGIN_TAB_TEXT).first.wait_for(state="visible", timeout=8000)
        except Exception:
            pass

        # 复刻 2.1 GetLoginPng 前置动作：收起面板残留 -> 切「扫码登录」标签 -> 点二维码容器
        try:
            page.locator(
                "#douyin_login_comp_flat_panel > div > div:nth-child(2) > div > div:nth-child(4) > p"
            ).click(timeout=1500)
        except Exception:
            pass
        try:
            page.get_by_text(LOGIN_TAB_TEXT).first.click(timeout=1500)
        except Exception:
            pass
        try:
            qr_container = page.locator(QR_CODE_SELECTOR).first
            qr_container.wait_for(state="visible", timeout=5000)
            qr_container.click(timeout=1500)
        except Exception:
            pass

        qr_started = time.perf_counter()
        qr_data = _wait_and_extract_qrcode(page, account_id=aid)
        logger.info(
            "[%s] 登录二维码提取结束，耗时 %.2fs，结果=%s",
            aid,
            time.perf_counter() - qr_started,
            "成功" if qr_data else "失败",
        )
        if not qr_data:
            raise RuntimeError("未能从页面提取到登录二维码，请稍后重试")
        _set(aid, session_id, status="waiting_scan", message="请使用抖音 App 扫码登录", qrcode=qr_data)

        deadline = time.time() + SESSION_TIMEOUT
        refresh_count = 0
        face_clicked = False
        polls = 0
        while time.time() < deadline:
            if _is_stopped(aid, session_id):
                raise CancelledError()

            cookies = context.cookies("https://www.douyin.com")
            if any(c.get("name") in _LOGIN_COOKIE_NAMES and c.get("value") for c in cookies):
                if not _save_state_if_current(context, aid, session_id):
                    raise CancelledError()
                nickname = _extract_profile_nickname(page)
                nickname_saved = _update_nickname_if_current(aid, session_id, nickname)
                if not _session_is_current(aid, session_id):
                    raise CancelledError()
                _set(aid, session_id, status="success",
                     message=(f"登录成功！已保存该账号的登录态（{len(cookies)} 条 Cookie）"
                              + (f"，账号：{nickname}" if nickname_saved else "")))
                logger.info("[%s] 网页扫码登录成功，state.json 已更新", aid)
                return

            polls += 1
            if polls % 10 == 0:
                names = ",".join(sorted({c.get("name", "") for c in cookies if c.get("name")}))
                logger.info("[%s] 等待扫码确认中，当前 Cookie：%s", aid, names or "无")

            if _qr_expired(page):
                refresh_count += 1
                if refresh_count > QR_REFRESH_LIMIT:
                    raise RuntimeError("二维码刷新次数过多，请重新发起扫码")
                logger.info("[%s] 登录二维码已过期，第 %s 次自动刷新", aid, refresh_count)
                _click_qr_refresh(page)
                page.wait_for_timeout(2500)
                qr_data = _wait_and_extract_qrcode(page, timeout_ms=30000, account_id=aid)
                if qr_data:
                    _set(aid, session_id, qrcode=qr_data,
                         message=f"二维码已自动刷新（第 {refresh_count} 次），请重新扫码")

            # 复刻 2.1 GetCooker 的二次刷脸风控处理：确认登录后可能要求刷脸，
            # 页面会展示新二维码供手机扫描，需持续提取并点击「已完成」
            if not face_clicked:
                if _js_click_first(page, ["手机刷脸验证", "刷脸验证"]):
                    face_clicked = True
                    logger.info("[%s] 触发二次安全验证，已点击刷脸按钮", aid)
                    _set(aid, session_id, message="触发安全验证：请用抖音 App 扫描下方新二维码并按提示完成验证")
                    page.wait_for_timeout(3000)
            else:
                _js_click_first(page, ["已完成", "验证成功"])
                qr_face = _extract_face_qr(page)
                if qr_face:
                    _set(aid, session_id, qrcode=qr_face)

            page.wait_for_timeout(1500)

        _set(aid, session_id, status="expired", message="扫码超时，请重新发起扫码", qrcode="")
        logger.info("[%s] 扫码会话超时结束", aid)

    except CancelledError:
        _set(aid, session_id, status="cancelled", message="已取消", qrcode="")
    except Exception as e:
        msg = str(e)[:200]
        _set(aid, session_id, status="failed", message="扫码会话异常", error=msg, qrcode="")
        logger.warning("[%s] 扫码会话异常：%s", aid, msg)
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        if xvfb_proc:
            try:
                xvfb_proc.terminate()
            except Exception:
                pass
        _release_slot_once(aid, session_id)
        with _guard:
            current = _sessions.get(aid)
            if current and current.get("session_id") == session_id and _stop_flags.get(aid) is stop_flag:
                _stop_flags.pop(aid, None)
        # 终态保留 120 秒供前端读取，之后仅清理本次会话，不能误删新会话。
        cleanup = threading.Timer(120, lambda: _cleanup_session(aid, session_id))
        cleanup.daemon = True
        cleanup.start()


def _cleanup_session(aid: str, session_id: str) -> None:
    with _guard:
        current = _sessions.get(aid)
        if current and current.get("session_id") == session_id:
            _sessions.pop(aid, None)


class CancelledError(Exception):
    pass


def _js_click_first(page, texts: list[str]) -> bool:
    """对包含指定文本的首个元素执行 JS 点击（绕过遮挡），成功返回 True。"""
    for t in texts:
        try:
            loc = page.get_by_text(t, exact=False)
            if loc.count():
                loc.first.evaluate("el => el.click()")
                return True
        except Exception:
            continue
    return False


_FACE_QR_JS = """
() => {
    const pick = (el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width < 100 || rect.width > 350 || Math.abs(rect.width - rect.height) > 15) return null;
        const src = el.src || "";
        if (src.includes("base64,")) return src;
        try {
            const c = document.createElement("canvas");
            c.width = el.naturalWidth || rect.width;
            c.height = el.naturalHeight || rect.height;
            c.getContext("2d").drawImage(el, 0, 0, c.width, c.height);
            return c.toDataURL("image/png");
        } catch (e) { return null; }
    };
    const imgs = document.querySelectorAll("img");
    for (let i = imgs.length - 1; i >= 0; i--) {
        const r = pick(imgs[i]);
        if (r) return r;
    }
    const canvases = document.querySelectorAll("canvas");
    for (let j = canvases.length - 1; j >= 0; j--) {
        const c = canvases[j];
        const rect = c.getBoundingClientRect();
        if (rect.width >= 100 && rect.width <= 350 && Math.abs(rect.width - rect.height) <= 15) {
            try { return c.toDataURL("image/png"); } catch (e) {}
        }
    }
    return null;
}
"""


def _extract_face_qr(page) -> str | None:
    """复刻 2.1 二次验证取码：按尺寸启发式扫描页面中的 img/canvas。"""
    try:
        data = page.evaluate(_FACE_QR_JS)
        return data if data and data.startswith("data:image") else None
    except Exception:
        return None


def _qrcode_locator_to_data_url(locator, src: str, account_id: str | None = None) -> str | None:
    """将二维码元素转换为 data URL，不额外从服务端下载二维码图片。"""
    started = time.perf_counter()
    if src.startswith("data:image"):
        if account_id:
            logger.info(
                "[%s] 登录二维码转换完成（页面 data URL），耗时 %.2fs",
                account_id,
                time.perf_counter() - started,
            )
        return src

    try:
        image = locator.screenshot(type="png", timeout=5000)
        data = "data:image/png;base64," + base64.b64encode(image).decode()
        if account_id:
            logger.info(
                "[%s] 登录二维码转换完成（元素截图），耗时 %.2fs",
                account_id,
                time.perf_counter() - started,
            )
        return data
    except Exception:
        # 保留旧版对已编码内容的兼容兜底；不再发起与页面独立的远程下载请求。
        if src:
            if account_id:
                logger.warning("[%s] 二维码元素截图失败，使用已编码源兜底", account_id)
            return f"data:image/png;base64,{src}"
    return None


def _wait_and_extract_qrcode(page, timeout_ms: int = 45000, account_id: str | None = None) -> str | None:
    """等待二维码出现并提取为 data URL；失败时整页截图兜底。

    容器冷启动首次加载可能超过 20s，窗口过短会把慢加载误判为失败。
    """
    deadline = time.time() + timeout_ms / 1000
    src = ""
    qr_locator = None
    while time.time() < deadline:
        for sel in _QR_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count():
                    first = loc.first
                    if first.is_visible():
                        candidate = first.get_attribute("src") or ""
                        if len(candidate) > 50:
                            src = candidate
                            qr_locator = first
                            break
            except Exception:
                continue
        if src:
            break
        # 二维码可能在 iframe 中
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            for sel in _QR_SELECTORS:
                try:
                    loc = frame.locator(sel)
                    if loc.count() and loc.first.is_visible():
                        candidate = loc.first.get_attribute("src") or ""
                        if len(candidate) > 50:
                            src = candidate
                            qr_locator = loc.first
                            break
                except Exception:
                    continue
            if src:
                break
        if src:
            break
        page.wait_for_timeout(800)

    if src and qr_locator:
        data = _qrcode_locator_to_data_url(qr_locator, src, account_id)
        if data:
            return data
    # 兜底：整页截图（用户至少能看到登录框与二维码）；渲染进程繁忙时可能瞬时失败，重试一次
    for _attempt in range(2):
        try:
            shot = page.screenshot(timeout=8000)
            return "data:image/png;base64," + base64.b64encode(shot).decode()
        except Exception:
            try:
                page.wait_for_timeout(1500)
            except Exception:
                break
    return None


def _qr_expired(page) -> bool:
    """检测二维码是否已过期（出现过期提示文本）。"""
    for text in _QR_EXPIRED_TEXTS:
        try:
            loc = page.get_by_text(text, exact=False)
            if loc.count():
                for i in range(min(loc.count(), 3)):
                    if loc.nth(i).is_visible():
                        return True
        except Exception:
            continue
    return False


def _click_qr_refresh(page) -> None:
    """点击二维码区域的刷新按钮重新出码。"""
    candidates = QR_CLICK_CANDIDATES
    for sel in candidates:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                return
        except Exception:
            continue
    try:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception:
        pass


def _save_state(context, account_id: str) -> None:
    """导出 storage_state 覆盖该账号 state.json（default 账号同步根目录副本）。"""
    if not persist_account_context(context, account_id):
        raise RuntimeError("登录成功后未检测到可持久化的会话 Cookie")
