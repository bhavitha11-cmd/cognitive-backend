from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import Optional

from pydantic import BaseModel, Field

# Re-use these from the holiday schema to avoid duplication
from app.schemas.holiday import ProjectDateOverride, TaskDateOverride


class PendingScheduleReviewResponse(BaseModel):
    """Full response object returned from the review API endpoints."""

    id: uuid.UUID
    holiday_id: uuid.UUID
    holiday_name: str
    holiday_date: date_type
    project_id: uuid.UUID
    project_name: str
    project_code: str
    project_manager_id: uuid.UUID | None
    project_manager_name: str | None = None
    review_status: str
    notes: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewApplyRequest(BaseModel):
    """Body sent by the Project Manager when accepting the proposed schedule.

    Mirrors EmergencyHolidayApplyRequest but is scoped to a single review.
    project_updates and task_updates may be empty — in that case the system
    applies no date changes (useful when shift_days == 0).
    """

    project_updates: list[ProjectDateOverride] = Field(default_factory=list, max_length=500)
    task_updates: list[TaskDateOverride] = Field(default_factory=list, max_length=500)


class ReviewRejectRequest(BaseModel):
    """Body sent by the Project Manager when rejecting the proposed schedule."""

    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional free-text reason for rejection",
    )
