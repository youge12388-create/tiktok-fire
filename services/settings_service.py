"""运行时可编辑的设置（当前为钉钉告警通道）。

优先级：网页端保存的设置 > 环境变量。这样管理员可以在后台直接改机器人配置，
不必登录服务器改 .env 再重启；环境变量仍作为首次部署与兜底来源。

安全约束：
- 加签密钥只写入 data/settings.json，任何接口响应都不得返回明文，只返回是否已设置；
- Webhook 地址只允许钉钉域名，避免把密钥外发到任意主机；
- 文件权限在 POSIX 上收紧为 0600。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import app_config

SETTINGS_PATH: Path = app_config.DATA_DIR / "settings.json"

# 钉钉自定义机器人的固定域名
_ALLOWED_HOSTS = {"oapi.dingtalk.com"}
_ALLOWED_HOST_SUFFIXES = (".dingtalk.com",)
SECRET_MASK = "******"
MAX_WEBHOOK_LENGTH = 2048
MAX_SECRET_LENGTH = 256

_lock = threading.RLock()


def _load_unlocked() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_unlocked(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_name(f"{SETTINGS_PATH.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, SETTINGS_PATH)


def load_settings() -> dict:
    with _lock:
        return dict(_load_unlocked())


def dingtalk_webhook_url() -> str:
    stored = str(load_settings().get("dingtalk_webhook_url") or "").strip()
    return stored or app_config.DINGTALK_WEBHOOK_URL


def dingtalk_secret() -> str:
    stored = str(load_settings().get("dingtalk_secret") or "").strip()
    return stored or app_config.DINGTALK_SECRET


def _host_allowed(host: str) -> bool:
    host = host.lower()
    return host in _ALLOWED_HOSTS or any(host.endswith(suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


def validate_webhook_url(url: str) -> str:
    """校验并规范化钉钉机器人 Webhook 地址；返回去空白后的地址。"""
    value = str(url or "").strip()
    if not value:
        return ""
    if len(value) > MAX_WEBHOOK_LENGTH:
        raise ValueError("Webhook 地址过长")
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise ValueError("Webhook 地址必须以 https:// 开头")
    if not parts.netloc or not _host_allowed(parts.hostname or ""):
        raise ValueError("Webhook 地址必须指向钉钉机器人域名（oapi.dingtalk.com）")
    if not dict(parse_qsl(parts.query, keep_blank_values=True)).get("access_token"):
        raise ValueError("Webhook 地址缺少 access_token 参数，请从钉钉机器人设置页完整复制")
    return value


def mask_webhook_url(url: str) -> str:
    """脱敏展示：仅保留域名与 access_token 的前后少量字符。

    直接在原始查询串里替换令牌，避免 re-encode 把掩码变成 ``%2A`` 影响可读性。
    """
    value = str(url or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    token = query.get("access_token", "")
    masked_query = parts.query
    if token:
        masked = f"{token[:4]}{SECRET_MASK}{token[-4:]}" if len(token) > 12 else SECRET_MASK
        masked_query = parts.query.replace(token, masked, 1)
    if parts.fragment:
        return f"{parts.scheme}://{parts.netloc}{parts.path}?{masked_query}#{parts.fragment}"
    return f"{parts.scheme}://{parts.netloc}{parts.path}?{masked_query}"


def notification_status() -> dict:
    """返回可安全展示的告警通道状态，绝不包含明文密钥。"""
    stored = load_settings()
    webhook = dingtalk_webhook_url()
    secret = dingtalk_secret()
    configured = bool(webhook and secret)
    source = "settings" if (stored.get("dingtalk_webhook_url") or stored.get("dingtalk_secret")) else ("env" if configured else "none")
    return {
        "configured": configured,
        "webhook_url": mask_webhook_url(webhook),
        "webhook_url_valid": bool(webhook) and not _url_problem(webhook),
        "secret_set": bool(secret),
        "source": source,
        "editable": True,
    }


def _url_problem(url: str) -> str:
    try:
        validate_webhook_url(url)
    except ValueError as exc:
        return str(exc)
    return ""


def update_notification_config(
    webhook_url: str | None = None,
    secret: str | None = None,
    clear: bool = False,
) -> dict:
    """保存钉钉配置。

    - ``clear=True``：清空网页端保存的配置，回退到环境变量；
    - 字段留空、传 None 或传脱敏掩码值：保持原值不变。

    掩码保护很关键：前端只拿到脱敏地址（``access_token=abcd******cdef``），
    若把掩码当新值存进去，告警通道会静默失效。
    """
    with _lock:
        data = _load_unlocked()
        if clear:
            data.pop("dingtalk_webhook_url", None)
            data.pop("dingtalk_secret", None)
        else:
            if webhook_url is not None:
                raw = str(webhook_url).strip()
                if raw and SECRET_MASK not in raw:
                    data["dingtalk_webhook_url"] = validate_webhook_url(raw)
            if secret is not None:
                value = str(secret).strip()
                if len(value) > MAX_SECRET_LENGTH:
                    raise ValueError("加签密钥过长")
                if value and value != SECRET_MASK:
                    data["dingtalk_secret"] = value
        _write_unlocked(data)
    return notification_status()
