from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.calendar_settings import CalendarSettings
from app.schemas.common import APIResponse


router = APIRouter(
    prefix="/calendar/settings",
    tags=["Calendar Settings"],
    dependencies=[Depends(get_current_user)],
)


class CalendarSettingsResponse(BaseModel):
    working_days: str
    weekend_days: str
    office_start_time: str
    office_end_time: str
    default_daily_hours: float
    working_hours_per_day: float

    model_config = {"from_attributes": True}


class CalendarSettingsUpdate(BaseModel):
    working_days: str | None = Field(None, max_length=100)
    weekend_days: str | None = Field(None, max_length=100)
    office_start_time: str | None = Field(None, max_length=5)
    office_end_time: str | None = Field(None, max_length=5)
    default_daily_hours: float | None = None
    working_hours_per_day: float | None = None


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Calendar", "view"))],
)
def get_settings(db: Session = Depends(get_db)):
    settings = db.scalar(select(CalendarSettings))
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar settings not configured",
        )
    return APIResponse(
        success=True,
        message="Calendar settings retrieved",
        data=CalendarSettingsResponse.model_validate(settings).model_dump(),
    )


@router.put(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "edit"))],
)
def update_settings(
    data: CalendarSettingsUpdate,
    db: Session = Depends(get_db),
):
    settings = db.scalar(select(CalendarSettings))
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar settings not configured",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)

    return APIResponse(
        success=True,
        message="Calendar settings updated",
        data=CalendarSettingsResponse.model_validate(settings).model_dump(),
    )
