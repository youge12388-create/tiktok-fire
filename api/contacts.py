"""联系人同步与读取。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from services import account_service, contact_service
from services.task_runtime import start_fetch_contacts

from .deps import require_admin

router = APIRouter(prefix="/accounts/{account_id}/contacts", tags=["contacts"], dependencies=[Depends(require_admin)])


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    names: list[str] = []
    contact_keys: list[str] = []


class DeleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    names: list[str] = []
    contact_keys: list[str] = []


def _resolve(account_id: str) -> str:
    try:
        return account_service.resolve(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
def list_contacts(account_id: str):
    return contact_service.list_contacts(_resolve(account_id))


@router.put("/selection")
def set_selection(account_id: str, body: SelectionBody):
    return contact_service.set_selection(_resolve(account_id), body.names, body.contact_keys)


@router.post("/delete")
def delete_selected(account_id: str, body: DeleteBody):
    return contact_service.delete_contacts(_resolve(account_id), body.names, body.contact_keys)


@router.post("/sync")
def sync_contacts(account_id: str):
    aid = _resolve(account_id)
    try:
        started = start_fetch_contacts(aid)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "started": started}
