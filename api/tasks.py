"""续火任务配置 / Dry Run / 手动执行 / 自动运行开关。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from services import account_service, spark_service

from .deps import require_admin

router = APIRouter(prefix="/accounts/{account_id}/spark-task", tags=["tasks"], dependencies=[Depends(require_admin)])


class TaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: dict


class AutoRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


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


@router.post("/auto-run")
def toggle_auto_run(account_id: str, body: AutoRunBody):
    aid = _resolve(account_id)
    merged = spark_service.set_auto_run(aid, body.enabled)
    return {"ok": True, "auto_run_enabled": bool(merged.get("auto_run_enabled"))}


@router.post("/stop")
def stop_run(account_id: str):
    aid = _resolve(account_id)
    return spark_service.stop(aid)
