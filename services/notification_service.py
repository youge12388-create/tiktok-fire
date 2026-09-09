"""外部告警通知：当前仅承载账号登录态失效的钉钉机器人通知。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import app_config
from core import accounts
from core.runtime import (
    claim_login_expired_alert,
    clear_login_expired_alert,
    finish_login_expired_alert,
    update_runtime,
)

logger = logging.getLogger("douyin-cloud-streak")


def dingtalk_configured() -> bool:
    return bool(app_config.DINGTALK_WEBHOOK_URL and app_config.DINGTALK_SECRET)


def _signed_webhook_url() -> str:
    """为钉钉加签 Webhook 添加 timestamp/sign，不记录含 token 的 URL。"""
    timestamp = str(int(time.time() * 1000))
    to_sign = f"{timestamp}\n{app_config.DINGTALK_SECRET}".encode("utf-8")
    sign = base64.b64encode(
        hmac.new(app_config.DINGTALK_SECRET.encode("utf-8"), to_sign, hashlib.sha256).digest()
    ).decode("utf-8")
    parts = urlsplit(app_config.DINGTALK_WEBHOOK_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"timestamp": timestamp, "sign": sign})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _post_dingtalk(content: str) -> bool:
    payload = json.dumps({"msgtype": "text", "text": {"content": content}}, ensure_ascii=False).encode("utf-8")
    request = Request(
        _signed_webhook_url(),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310 - URL is explicit administrator configuration
            body = json.loads(response.read().decode("utf-8") or "{}")
        return int(body.get("errcode", -1)) == 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("钉钉登录失效告警投递失败：%s", str(exc)[:160])
        return False


def report_session_expired(account_id: str, reason: str) -> bool:
    """记录掉线并至多通知一次。通知故障不影响抖音任务主流程。"""
    update_runtime(account_id, session_status="expired")
    if not dingtalk_configured():
        logger.warning("[%s] 账号登录态失效，但未配置完整钉钉 Webhook，未发送告警", account_id)
        return False
    if not claim_login_expired_alert(account_id, reason):
        return False

    account = accounts.get_account(account_id) or {}
    label = account.get("name") or account_id
    delivered = _post_dingtalk(
        f"【抖音续火花】账号需要重新登录\n账号：{label}\n账号 ID：{account_id}\n原因：{str(reason)[:300]}"
    )
    finish_login_expired_alert(account_id, delivered)
    if delivered:
        logger.info("[%s] 已发送钉钉登录失效告警", account_id)
    return delivered


def report_session_ok(account_id: str) -> None:
    """仅由已确认登录成功的路径调用，避免未知状态误解除告警。"""
    update_runtime(account_id, session_status="ok")
    clear_login_expired_alert(account_id)


def send_test_notification() -> tuple[bool, str]:
    """主动验证钉钉机器人配置；不占用账号掉线告警的去重状态。"""
    if not dingtalk_configured():
        return False, "钉钉告警未完整配置，请设置 Webhook 地址和加签密钥"
    content = (
        "【抖音续火花】告警通道测试\n"
        "如果你看到这条消息，账号掉线通知通道配置正常。\n"
        f"测试时间：{datetime.now().astimezone().isoformat(timespec='seconds')}"
    )
    if not _post_dingtalk(content):
        logger.warning("钉钉告警测试发送失败")
        return False, "钉钉测试消息发送失败，请检查机器人配置和安全设置"
    logger.info("钉钉告警测试发送成功")
    return True, "测试消息已发送，请在钉钉群中确认收到"
