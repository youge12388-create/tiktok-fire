"""运行历史 / 明细查询。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from services import run_service

from .deps import require_admin

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_admin)])


@router.get("")
def list_runs(
    account_id: str | None = None,
    status: str | None = None,
    date: str | None = None,
    risk: str | None = None,
    limit: int = Query(200, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    # 前端清除筛选时可能送出空串，按「不过滤」处理，避免无意义的 422。
    return run_service.list_runs(account_id, status, date, limit, offset, _parse_risk(risk))


def _parse_risk(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise HTTPException(status_code=422, detail="risk 必须是布尔值")


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
