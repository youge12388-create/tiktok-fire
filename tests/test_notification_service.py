from __future__ import annotations

import json

import app_config
from core.runtime import load_runtime
from services import notification_service


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"errcode": 0}).encode()


def test_login_expired_notification_is_signed_and_deduplicated(monkeypatch):
    monkeypatch.setattr(app_config, "DINGTALK_WEBHOOK_URL", "https://example.test/robot/send?access_token=token")
    monkeypatch.setattr(app_config, "DINGTALK_SECRET", "SEC-not-a-real-secret")
    sent = []

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.data, timeout))
        return _Response()

    monkeypatch.setattr(notification_service, "urlopen", fake_urlopen)

    account_id = "notification-dedupe"
    notification_service.report_session_ok(account_id)
    assert notification_service.report_session_expired(account_id, "页面出现登录二维码") is True
    assert notification_service.report_session_expired(account_id, "重复检测") is False
    assert len(sent) == 1
    assert "timestamp=" in sent[0][0] and "sign=" in sent[0][0]
    assert "页面出现登录二维码".encode("utf-8") in sent[0][1]
    assert load_runtime(account_id)["login_expired_alert"]["delivered"] is True


def test_login_recovery_rearms_next_expired_notification(monkeypatch):
    monkeypatch.setattr(app_config, "DINGTALK_WEBHOOK_URL", "https://example.test/robot/send?access_token=token")
    monkeypatch.setattr(app_config, "DINGTALK_SECRET", "SEC-not-a-real-secret")
    monkeypatch.setattr(notification_service, "_post_dingtalk", lambda _content: True)

    account_id = "notification-recovery"
    notification_service.report_session_ok(account_id)
    notification_service.report_session_expired(account_id, "登录失效")
    notification_service.report_session_ok(account_id)
    assert "login_expired_alert" not in load_runtime(account_id)
    assert notification_service.report_session_expired(account_id, "再次失效") is True


def test_notification_test_message_uses_configured_channel_without_dedupe(monkeypatch):
    monkeypatch.setattr(app_config, "DINGTALK_WEBHOOK_URL", "https://example.test/robot/send?access_token=token")
    monkeypatch.setattr(app_config, "DINGTALK_SECRET", "SEC-not-a-real-secret")
    messages = []
    monkeypatch.setattr(notification_service, "_post_dingtalk", lambda content: messages.append(content) or True)

    ok, message = notification_service.send_test_notification()

    assert ok is True
    assert "测试消息已发送" in message
    assert len(messages) == 1
    assert "抖音续火花" in messages[0]
    assert "告警通道测试" in messages[0]


def test_notification_test_message_reports_missing_configuration(monkeypatch):
    monkeypatch.setattr(app_config, "DINGTALK_WEBHOOK_URL", "")
    monkeypatch.setattr(app_config, "DINGTALK_SECRET", "")

    ok, message = notification_service.send_test_notification()

    assert ok is False
    assert "未完整配置" in message
