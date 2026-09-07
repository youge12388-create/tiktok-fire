"""应用级配置与安全校验。

集中读取 .env（ADMIN_PASSWORD / SESSION_SECRET / 端口 / Cookie 等），
并在启动阶段做 fail-fast 校验，杜绝默认弱口令与缺失密钥。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.environ.get("DOUYIN_DATA_DIR", str(BASE_DIR / "data")))

# 弱口令黑名单（大小写不敏感），避免 admin/123456 这类默认值
WEAK_PASSWORDS = {
    "",
    "admin",
    "123456",
    "password",
    "change_me",
    "admin123",
    "spark_secret_token_change_me",
    "spark_secret_token",
}

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", str(7 * 24 * 3600)))


def _normalize_public_base_path(value: str) -> str:
    """规范化可选的反向代理挂载前缀；根路径统一用空串表示。"""
    path = value.strip()
    if path in {"", "/"}:
        return ""
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "//" in path
        or any(char in path for char in ("?", "#", "\\"))
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        return path
    return path.rstrip("/")


def _is_safe_url_path(value: str, *, allow_empty: bool) -> bool:
    if not value:
        return allow_empty
    return (
        value.startswith("/")
        and not value.startswith("//")
        and "//" not in value
        and not any(char in value for char in ("?", "#", "\\"))
        and all(part not in {".", ".."} for part in value.split("/"))
    )


PUBLIC_BASE_PATH = _normalize_public_base_path(os.getenv("PUBLIC_BASE_PATH", ""))
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session").strip() or "session"
_DEFAULT_SESSION_COOKIE_PATH = f"{PUBLIC_BASE_PATH}/" if PUBLIC_BASE_PATH else "/"
SESSION_COOKIE_PATH = os.getenv("SESSION_COOKIE_PATH", _DEFAULT_SESSION_COOKIE_PATH).strip() or _DEFAULT_SESSION_COOKIE_PATH

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"


def security_problems() -> list[str]:
    """返回配置中的安全问题列表；为空表示可启动。"""
    problems: list[str] = []
    if not ADMIN_PASSWORD:
        problems.append("ADMIN_PASSWORD 未配置，请在 .env 中设置管理员密码")
    elif ADMIN_PASSWORD.lower() in WEAK_PASSWORDS:
        problems.append("ADMIN_PASSWORD 过弱，不能使用 admin/123456/password 等默认密码")
    if not SESSION_SECRET or len(SESSION_SECRET) < 32:
        problems.append("SESSION_SECRET 缺失或过短，请设置至少 32 位随机字符串")
    if not _is_safe_url_path(PUBLIC_BASE_PATH, allow_empty=True):
        problems.append("PUBLIC_BASE_PATH 必须是以 / 开头的路径前缀，例如 /douyin-fire")
    if not _is_safe_url_path(SESSION_COOKIE_PATH, allow_empty=False):
        problems.append("SESSION_COOKIE_PATH 必须是以 / 开头的 Cookie 路径")
    return problems
