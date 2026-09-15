"""后台可编辑的钉钉告警配置：校验、脱敏、优先级与接口权限。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from services import notification_service, settings_service

VALID_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=abc1234567890abc"

# 与 conftest 一致：使用 tests/_tmp_data 下的独立文件，避免依赖系统临时目录。
_SETTINGS_DIR = Path(__file__).resolve().parent / "_tmp_data" / "settings-tests"


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch):
    """每个用例使用独立的 settings.json，且不受环境变量干扰。"""
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SETTINGS_DIR / "settings.json"
    path.unlink(missing_ok=True)
    monkeypatch.setattr(settings_service, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_WEBHOOK_URL", "")
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_SECRET", "")
    yield path
    path.unlink(missing_ok=True)


def test_saving_config_makes_channel_configured():
    assert notification_service.dingtalk_configured() is False

    status = settings_service.update_notification_config(VALID_WEBHOOK, "SEC-not-a-real-secret")

    assert status["configured"] is True
    assert status["secret_set"] is True
    assert status["source"] == "settings"
    assert notification_service.dingtalk_configured() is True


def test_status_never_returns_plaintext_secret_or_token():
    settings_service.update_notification_config(VALID_WEBHOOK, "SEC-super-secret-value")

    status = settings_service.notification_status()
    serialized = json.dumps(status, ensure_ascii=False)

    assert "SEC-super-secret-value" not in serialized
    # access_token 也要脱敏，只保留首尾少量字符。
    assert "abc1234567890abc" not in serialized
    assert "******" in status["webhook_url"]


def test_stored_value_takes_priority_over_env(monkeypatch):
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=env-token-000")
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_SECRET", "SEC-env")

    assert settings_service.dingtalk_webhook_url().endswith("env-token-000")

    settings_service.update_notification_config(VALID_WEBHOOK, None)

    # 保存后覆盖环境变量，但密钥留空时仍沿用环境变量。
    assert settings_service.dingtalk_webhook_url() == VALID_WEBHOOK
    assert settings_service.dingtalk_secret() == "SEC-env"


def test_blank_secret_keeps_existing_value():
    settings_service.update_notification_config(VALID_WEBHOOK, "SEC-first")
    settings_service.update_notification_config(None, "   ")

    assert settings_service.dingtalk_secret() == "SEC-first"


def test_blank_or_masked_webhook_keeps_existing_value():
    """前端只拿到脱敏地址；把留空或掩码值提交回来不能覆盖真实配置。"""
    settings_service.update_notification_config(VALID_WEBHOOK, "SEC-first")

    settings_service.update_notification_config(None, None)
    assert settings_service.dingtalk_webhook_url() == VALID_WEBHOOK

    masked = settings_service.notification_status()["webhook_url"]
    assert "******" in masked
    settings_service.update_notification_config(masked, None)

    # 掩码不是有效令牌，必须保持原地址，否则告警会静默失效。
    assert settings_service.dingtalk_webhook_url() == VALID_WEBHOOK
    assert notification_service.dingtalk_configured() is True


def test_clear_falls_back_to_env(monkeypatch):
    settings_service.update_notification_config(VALID_WEBHOOK, "SEC-saved")
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?access_token=env-token-000")
    monkeypatch.setattr(settings_service.app_config, "DINGTALK_SECRET", "SEC-env")

    status = settings_service.update_notification_config(clear=True)

    assert status["source"] == "env"
    assert settings_service.dingtalk_webhook_url().endswith("env-token-000")


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://oapi.dingtalk.com/robot/send?access_token=x",
        "https://evil.example.com/robot/send?access_token=x",
        "https://oapi.dingtalk.com/robot/send",
    ],
)
def test_invalid_webhook_urls_are_rejected(bad_url):
    with pytest.raises(ValueError):
        settings_service.update_notification_config(bad_url, "SEC-x")


def test_settings_file_is_not_world_readable_on_posix(_clean_settings):
    settings_service.update_notification_config(VALID_WEBHOOK, "SEC-x")
    path = settings_service.SETTINGS_PATH
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["dingtalk_secret"] == "SEC-x"
    if os.name == "posix":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_settings_api_requires_login_and_masks_secret(client, monkeypatch):
    # 未登录不可读写
    assert client.get("/api/v1/system/notifications/status").status_code == 401

    client.post("/api/v1/auth/login", json={"username": "admin", "password": "T3st-Strong-Passw0rd!"})
    saved = client.put(
        "/api/v1/system/notifications/config",
        json={"webhook_url": VALID_WEBHOOK, "secret": "SEC-from-api"},
    )

    assert saved.status_code == 200
    body = saved.json()["dingtalk"]
    assert body["configured"] is True
    assert "SEC-from-api" not in json.dumps(body, ensure_ascii=False)

    status = client.get("/api/v1/system/notifications/status")
    assert status.json()["dingtalk"]["secret_set"] is True


def test_settings_api_rejects_non_dingtalk_url(client):
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "T3st-Strong-Passw0rd!"})
    response = client.put(
        "/api/v1/system/notifications/config",
        json={"webhook_url": "https://example.com/robot/send?access_token=x", "secret": "SEC-x"},
    )

    assert response.status_code == 400
    assert "钉钉" in response.json()["detail"]
