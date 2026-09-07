"""管理员登录 / 登出 / 会话校验。"""

from __future__ import annotations

import hmac
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app_config import ADMIN_PASSWORD, ADMIN_USERNAME

from .deps import require_admin

router = APIRouter(prefix="/auth", tags=["auth"])

_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_FAILURES = 5
_LOGIN_BLOCK_SECONDS = 300
_login_failures: dict[str, deque[float]] = {}
_login_blocked_until: dict[str, float] = {}
_login_guard = threading.Lock()


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_login_blocked(key: str, now: float) -> bool:
    with _login_guard:
        blocked_until = _login_blocked_until.get(key)
        if blocked_until is not None:
            if now < blocked_until:
                return True
            _login_blocked_until.pop(key, None)
        attempts = _login_failures.get(key)
        if not attempts:
            return False
        cutoff = now - _LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            _login_failures.pop(key, None)
            return False
        return len(attempts) >= _LOGIN_MAX_FAILURES and now - attempts[-1] < _LOGIN_BLOCK_SECONDS


def _record_login_failure(key: str, now: float) -> None:
    with _login_guard:
        attempts = _login_failures.setdefault(key, deque())
        cutoff = now - _LOGIN_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        attempts.append(now)
        if len(attempts) >= _LOGIN_MAX_FAILURES:
            _login_blocked_until[key] = now + _LOGIN_BLOCK_SECONDS
        # 防止请求来源不断变化时这张进程内表无限增长。
        if len(_login_failures) > 2048:
            for stale_key, stale in list(_login_failures.items()):
                if (
                    (not stale or now - stale[-1] >= _LOGIN_BLOCK_SECONDS)
                    and now >= _login_blocked_until.get(stale_key, 0)
                ):
                    _login_failures.pop(stale_key, None)
                    _login_blocked_until.pop(stale_key, None)


def _clear_login_failures(key: str) -> None:
    with _login_guard:
        _login_failures.pop(key, None)
        _login_blocked_until.pop(key, None)


@router.post("/login")
def login(body: LoginBody, request: Request):
    now = time.monotonic()
    key = _client_key(request)
    if _is_login_blocked(key, now):
        return JSONResponse(
            {"detail": "登录尝试过于频繁，请 5 分钟后再试"},
            status_code=429,
            headers={"Retry-After": str(_LOGIN_BLOCK_SECONDS)},
        )

    # compare_digest 对非 ASCII str 会抛 TypeError；编码后比较既支持中文账号/密码，
    # 也避免把恶意 Unicode 输入变成 500。
    user_ok = hmac.compare_digest(body.username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8"))
    pass_ok = hmac.compare_digest(body.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))
    if not (user_ok and pass_ok):
        _record_login_failure(key, now)
        return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
    _clear_login_failures(key)
    request.session["admin"] = body.username
    request.session["authenticated"] = True
    return {"ok": True, "username": body.username}


@router.post("/logout")
def logout(request: Request, _admin: str = Depends(require_admin)):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(admin: str = Depends(require_admin)):
    return {"ok": True, "username": admin}
