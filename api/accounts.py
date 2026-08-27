"""账号管理 + 扫码登录 + 登录状态检测。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from services import account_service
from services.douyin import douyin
from services.task_runtime import start_harvest_creator

from .deps import require_admin

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(require_admin)])


class AccountBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    device: str = ""
    enabled: bool | None = None


def _resolve(account_id: str) -> str:
    try:
        return account_service.resolve(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_accounts():
    return account_service.list_accounts()


@router.post("")
def create_account(body: AccountBody):
    return account_service.create_account(name=body.name, device=body.device)


@router.patch("/{account_id}")
def update_account(account_id: str, body: AccountBody):
    aid = _resolve(account_id)
    acc = account_service.update_account(aid, name=body.name or None, device=body.device or None, enabled=body.enabled)
    if acc is None:
        raise HTTPException(status_code=400, detail="默认账号不允许停用/删除")
    return {"ok": True, "account": acc}


@router.delete("/{account_id}")
def delete_account(account_id: str):
    aid = _resolve(account_id)
    try:
        account_service.delete_account(aid)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{account_id}/login/start")
def login_start(account_id: str):
    return douyin.scan_start(_resolve(account_id))


@router.get("/{account_id}/login/status")
def login_status(account_id: str):
    return douyin.scan_status(_resolve(account_id))


@router.post("/{account_id}/login/cancel")
def login_cancel(account_id: str):
    return douyin.scan_cancel(_resolve(account_id))


@router.post("/{account_id}/check-login")
def check_login(account_id: str):
    return douyin.check_login_status(_resolve(account_id))


@router.post("/{account_id}/harvest-creator")
def harvest_creator(account_id: str):
    aid = _resolve(account_id)
    try:
        start_harvest_creator(aid)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}
