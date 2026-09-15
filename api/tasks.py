"""续火任务配置 / Dry Run / 手动执行 / 自动运行开关 / 核对与补发。"""

from __future__ import annotations

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services import account_service, reconcile_service, spark_service

from .deps import require_admin

router = APIRouter(prefix="/accounts/{account_id}/spark-task", tags=["tasks"], dependencies=[Depends(require_admin)])


def _valid_date(date: str | None) -> str | None:
    """只接受 YYYY-MM-DD，避免把任意字符串拼进 LIKE 查询。"""
    if not date:
        return None
    try:
        return date_type.fromisoformat(date).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date 必须是 YYYY-MM-DD 格式") from exc


class TaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: dict


class AutoRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class RetryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 留空表示按「今日确定失败」自动取名单；显式传入时只补发名单内的人。
    names: list[str] = Field(default_factory=list, max_length=500)


def _resolve(account_id: str) -> str:
    try:
        return account_service.resolve(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _run(fn):
    try:
        return fn()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def get_task(account_id: str):
    return spark_service.get_task(_resolve(account_id))


@router.put("")
def put_task(account_id: str, body: TaskBody):
    aid = _resolve(account_id)
    return _run(lambda: spark_service.put_task(aid, body.config))


@router.post("/dry-run")
def dry_run(account_id: str):
    aid = _resolve(account_id)
    return _run(lambda: spark_service.dry_run(aid))


@router.post("/run")
def run(account_id: str):
    aid = _resolve(account_id)
    return _run(lambda: spark_service.run(aid))


@router.get("/reconcile")
def reconcile(account_id: str, date: str | None = None):
    """核对当前勾选名单今日是否全部续火成功，并列出失败的人与原因。"""
    aid = _resolve(account_id)
    return reconcile_service.account_report(aid, _valid_date(date))


@router.post("/retry")
def retry(account_id: str, body: RetryBody | None = None):
    """只补发指定联系人（默认取今日确定失败的人），不会重发整份名单。"""
    aid = _resolve(account_id)
    return _run(lambda: spark_service.retry(aid, body.names if body else None))


@router.post("/auto-run")
def toggle_auto_run(account_id: str, body: AutoRunBody):
    aid = _resolve(account_id)
    merged = spark_service.set_auto_run(aid, body.enabled)
    return {"ok": True, "auto_run_enabled": bool(merged.get("auto_run_enabled"))}


@router.post("/stop")
def stop_run(account_id: str):
    aid = _resolve(account_id)
    return spark_service.stop(aid)
