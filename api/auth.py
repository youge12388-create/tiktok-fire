"""管理员登录 / 登出 / 会话校验。"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app_config import ADMIN_PASSWORD, ADMIN_USERNAME

from .deps import require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request):
    user_ok = hmac.compare_digest(body.username, ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(body.password, ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
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
