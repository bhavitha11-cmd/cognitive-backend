from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class TodayEvent(BaseModel):
    id: str
    title: str
    type: str
    date: str
    color: str | None = None


class BirthdayInfo(BaseModel):
    id: uuid.UUID
    name: str
    department: str | None = None


class HolidayInfo(BaseModel):
    id: uuid.UUID
    name: str
    date: date
    holiday_type: str


class TaskDueInfo(BaseModel):
    id: uuid.UUID
    task_code: str
    title: str
    project_name: str | None = None
    status: str


class ProjectDeliveryInfo(BaseModel):
    id: uuid.UUID
    name: str
    planned_end_date: date
    project_manager: str | None = None
    is_delayed: bool = False


class DelayedTaskInfo(BaseModel):
    id: uuid.UUID
    task_code: str
    title: str
    project_name: str | None = None
    days_overdue: int
    assigned_to: str | None = None
