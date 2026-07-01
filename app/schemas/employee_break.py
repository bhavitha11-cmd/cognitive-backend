from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import APIResponse


class BreakStartRequest(BaseModel):
    remarks: str | None = Field(None, max_length=500)


class BreakEndRequest(BaseModel):
    remarks: str | None = Field(None, max_length=500)


class BreakRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    break_start: datetime
    break_end: datetime | None = None
    duration_minutes: int
    date: date
    remarks: str | None = Field(None, max_length=500)
    created_at: datetime


class BreakResponse(APIResponse):
    data: BreakRead | None = None


class BreakListResponse(APIResponse):
    data: list[BreakRead] | None = None
