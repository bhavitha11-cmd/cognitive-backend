from __future__ import annotations

import uuid
from datetime import date, datetime

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


class PendingScheduleReviewWidget(BaseModel):
    """Compact representation used by the Pending Schedule Reviews dashboard widget.

    Contains enough information to render each widget card and to navigate to
    the full impact analysis page (identified by ``id`` and ``holiday_id``).
    """

    id: uuid.UUID
    holiday_id: uuid.UUID
    holiday_name: str
    holiday_date: date
    project_id: uuid.UUID
    project_name: str
    project_code: str
    review_status: str          # always "PENDING" in the widget context
    project_manager_name: str | None = None
    created_at: datetime
