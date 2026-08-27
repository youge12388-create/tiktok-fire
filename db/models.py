"""SQLite 行模型与 Pydantic 响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# 运行/明细状态（§19：success / failed / uncertain）
RunStatus = Literal["success", "failed", "uncertain"]


class RunRecordOut(BaseModel):
    id: int
    account_id: str
    task_type: str
    started_at: str | None = None
    finished_at: str | None = None
    status: str
    success_count: int = 0
    failed_count: int = 0
    risk_detected: bool = False
    error: str | None = None


class RunItemOut(BaseModel):
    id: int
    run_id: int
    account_id: str
    friend_name: str
    message_type: str | None = None
    message_preview: str | None = None
    status: str
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RunDetailOut(RunRecordOut):
    items: list[RunItemOut] = []
