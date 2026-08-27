"""运行历史 / 明细查询。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from services import run_service

from .deps import require_admin

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_admin)])


@router.get("")
def list_runs(account_id: str | None = None, status: str | None = None, date: str | None = None, limit: int = 200, offset: int = 0):
    return run_service.list_runs(account_id, status, date, limit, offset)


@router.get("/{run_id}")
def get_run(run_id: int):
    rec = run_service.get_run(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return rec


@router.get("/{run_id}/artifact")
def get_run_artifact(run_id: int):
    rec = run_service.get_run(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    path = run_service.artifact_path(rec.get("account_id"), rec.get("started_at"), run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="该运行没有保存截图")
    return FileResponse(str(path), media_type="image/png")
