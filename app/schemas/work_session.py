from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import APIResponse


class WorkSessionCreate(BaseModel):
    task_id: uuid.UUID
    project_id: uuid.UUID
    session_type: str = Field(default="REGULAR", max_length=20)


class WorkSessionPause(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class WorkSessionUpdate(BaseModel):
    end_time: datetime | None = None
    remarks: str | None = None
    pause_reason: str | None = None


class WorkSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    task_id: uuid.UUID
    project_id: uuid.UUID
    session_type: str
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int
    status: str
    started_by: uuid.UUID | None = None
    ended_by: uuid.UUID | None = None
    pause_reason: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime


class ActiveSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    project_id: uuid.UUID
    session_type: str
    start_time: datetime
    elapsed_minutes: int
    pause_reason: str | None = None


class DailySessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    total_session_minutes: int
    total_break_minutes: int
    net_work_minutes: int
    session_count: int


class WorkSessionResponse(APIResponse):
    data: WorkSessionRead | None = None


class WorkSessionListResponse(APIResponse):
    data: list[WorkSessionRead] | None = None


class ActiveSessionListResponse(APIResponse):
    data: list[ActiveSessionResponse] | None = None


class DailySessionSummaryResponse(APIResponse):
    data: DailySessionSummary | None = None
