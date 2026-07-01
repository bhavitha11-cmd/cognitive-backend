from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_ENTRY_TYPES = {"REGULAR", "OVERTIME", "CORRECTION"}
VALID_STATUSES = {"DRAFT", "SUBMITTED", "APPROVED", "REJECTED"}


class TimeEntryCreate(BaseModel):
    employee_id: Optional[uuid.UUID] = Field(None, description="If provided, overridden by authenticated user ID server-side")
    task_id: uuid.UUID
    date: date_type
    hours_spent: float = Field(gt=0, le=24)
    description: Optional[str] = Field(default=None, max_length=2000)
    entry_type: str = "REGULAR"
    is_billable: bool = True

    @field_validator("entry_type")
    @classmethod
    def validate_entry_type(cls, v: str) -> str:
        if v not in VALID_ENTRY_TYPES:
            raise ValueError(f"entry_type must be one of {sorted(VALID_ENTRY_TYPES)}")
        return v


class TimeEntryUpdate(BaseModel):
    date: Optional[date_type] = None
    hours_spent: Optional[float] = Field(default=None, gt=0, le=24)
    description: Optional[str] = Field(default=None, max_length=2000)
    entry_type: Optional[str] = None
    is_billable: Optional[bool] = None

    @field_validator("entry_type")
    @classmethod
    def validate_entry_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ENTRY_TYPES:
            raise ValueError(f"entry_type must be one of {sorted(VALID_ENTRY_TYPES)}")
        return v


class TimeEntryResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    task_id: uuid.UUID
    task_code: Optional[str] = None
    task_title: Optional[str] = None
    project_id: uuid.UUID
    project_name: Optional[str] = None
    date: date_type
    hours_spent: float
    description: Optional[str]
    entry_type: str
    is_billable: bool
    status: str
    submitted_at: Optional[datetime]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TimesheetSummary(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    period_start: date_type
    period_end: date_type
    total_hours: float
    billable_hours: float
    approved_hours: float
    by_project: list[dict]
    by_task: list[dict]


class TimeEntryCreateBatch(BaseModel):
    entries: list[TimeEntryCreate] = Field(min_length=1, max_length=50)


class RejectTimeEntryRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
