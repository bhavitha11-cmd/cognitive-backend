from __future__ import annotations

import re
import uuid
from datetime import date as date_type
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

VALID_STATUSES = {"PRESENT", "ABSENT", "HALF_DAY", "WFH", "ON_LEAVE", "HOLIDAY"}

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _validate_hhmm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    if not _TIME_RE.match(value):
        raise ValueError("Time must be in HH:MM format (e.g. '09:00')")
    h, m = value.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError("Time value out of range")
    return value


# ── Attendance Rule schemas ───────────────────────────────────────────────────

class AttendanceRuleUpdate(BaseModel):
    office_start_time: Optional[str] = None
    office_end_time: Optional[str] = None
    half_day_hours: Optional[float] = None
    late_mark_after_minutes: Optional[int] = None
    work_days: Optional[str] = None
    required_productive_hours: Optional[float] = None
    overtime_threshold_hours: Optional[float] = None
    max_break_minutes: Optional[int] = None
    min_break_minutes: Optional[int] = None

    @field_validator("office_start_time", mode="before")
    @classmethod
    def validate_start_time(cls, v):
        return _validate_hhmm(v)

    @field_validator("office_end_time", mode="before")
    @classmethod
    def validate_end_time(cls, v):
        return _validate_hhmm(v)


class AttendanceRuleResponse(BaseModel):
    id: uuid.UUID
    office_start_time: str
    office_end_time: str
    half_day_hours: float
    late_mark_after_minutes: int
    work_days: str
    required_productive_hours: float
    overtime_threshold_hours: float
    max_break_minutes: int
    min_break_minutes: int

    model_config = ConfigDict(from_attributes=True)


# ── Attendance Mark schemas ───────────────────────────────────────────────────

class AttendanceMarkRequest(BaseModel):
    employee_id: uuid.UUID
    date: date_type
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    status: str = "PRESENT"
    notes: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v


class AttendanceBulkMarkRequest(BaseModel):
    date: date_type
    records: list[AttendanceMarkRequest]


# ── Attendance Response schema ────────────────────────────────────────────────

class AttendanceResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    date: date_type
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    total_hours: float
    status: str
    is_late: bool
    late_by_minutes: int
    overtime_hours: float
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
