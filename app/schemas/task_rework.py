from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import APIResponse


class TaskReworkCreate(BaseModel):
    task_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)
    hours_spent: float = Field(default=0, ge=0, le=1000)


class TaskReworkClose(BaseModel):
    hours_spent: float = Field(..., ge=0, le=1000)


class TaskReworkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    rework_number: int
    opened_by: uuid.UUID | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    reason: str | None = None
    hours_spent: float
    created_at: datetime


class TaskReworkResponse(APIResponse):
    data: TaskReworkRead | None = None


class TaskReworkListResponse(APIResponse):
    data: list[TaskReworkRead] | None = None
