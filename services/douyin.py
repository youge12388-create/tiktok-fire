"""DouyinService：唯一封装 core 抖音自动化/Playwright 调用的适配器。

api/ 与其他 services 禁止直接 import core 的 Playwright 细节，
统一经由此适配层调用，为后续自动回复 / 视频转发等扩展留缝。
"""

from __future__ import annotations

from core import automation, login_session, scheduler
from core.config import get_valid_state_path
from core.runtime import update_runtime

from .notification_service import report_session_expired, report_session_ok


class DouyinService:
    def run_spark(self, account_id: str, dry_run: bool = False, only_names: list[str] | None = None) -> dict:
        """执行续火任务（dry_run=True 时不发送真实消息）。"""
        return automation.run_send(dry_run=dry_run, only_names=only_names, account_id=account_id)

    def fetch_contacts(self, account_id: str, supplement: bool = False) -> dict:
        """同步抖音私信页聊天联系人；supplement 表示补充上一趟未完成扫描。"""
        return automation.fetch_chat_contacts(account_id, supplement=supplement)

    def scan_start(self, account_id: str) -> dict:
        return login_session.start(account_id)

    def scan_status(self, account_id: str) -> dict:
        return login_session.status(account_id)

    def scan_cancel(self, account_id: str) -> dict:
        return login_session.cancel(account_id)

    def check_login_status(self, account_id: str) -> dict:
        """检测登录态：优先校验 state 文件，必要时打开浏览器真实检测。"""
        state_path = get_valid_state_path(account_id)
        if state_path is None:
            report_session_expired(account_id, "未找到有效登录态 state.json")
            return {
                "logged_in": False,
                "reason": "未找到有效登录态 state.json",
                "session_status": "expired",
            }
        try:
            from core.automation import CHAT_URL, check_login
            from core.browser import open_browser

            with open_browser(state_path=state_path) as (p, browser, context, page):
                page.goto(CHAT_URL, timeout=90000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                logged, why = check_login(page)
                if logged:
                    report_session_ok(account_id)
                else:
                    report_session_expired(account_id, why)
                return {
                    "logged_in": logged,
                    "reason": why,
                    "session_status": "ok" if logged else "expired",
                }
        except Exception as exc:  # noqa: BLE001
            update_runtime(account_id, session_status="unknown")
            return {"logged_in": False, "reason": f"检测异常: {exc}", "session_status": "unknown"}

    def next_run_time(self, account_id: str) -> str | None:
        return scheduler.next_run_time(account_id)

    def next_harvest_time(self, account_id: str) -> str | None:
        return scheduler.next_harvest_time(account_id)


douyin = DouyinService()
