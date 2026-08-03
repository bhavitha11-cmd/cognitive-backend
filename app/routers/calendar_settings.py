from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
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

_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


class CalendarSettingsResponse(BaseModel):
    working_days: str
    weekend_days: str
    weekly_off_rules: dict | None = None
    office_start_time: str
    office_end_time: str
    default_daily_hours: float
    working_hours_per_day: float
    enable_birthdays: bool
    enable_company_events: bool
    enable_holidays: bool
    enable_task_events: bool
    enable_project_events: bool
    color_holiday: str
    color_birthday: str
    color_task: str
    color_project: str
    color_company_event: str

    model_config = {"from_attributes": True}


class CalendarSettingsUpdate(BaseModel):
    working_days: str | None = Field(None, max_length=100)
    weekend_days: str | None = Field(None, max_length=100)
    weekly_off_rules: dict | None = None
    office_start_time: str | None = Field(None, max_length=5)
    office_end_time: str | None = Field(None, max_length=5)
    default_daily_hours: float | None = None
    working_hours_per_day: float | None = None
    enable_birthdays: bool | None = None
    enable_company_events: bool | None = None
    enable_holidays: bool | None = None
    enable_task_events: bool | None = None
    enable_project_events: bool | None = None
    color_holiday: str | None = Field(None, max_length=7)
    color_birthday: str | None = Field(None, max_length=7)
    color_task: str | None = Field(None, max_length=7)
    color_project: str | None = Field(None, max_length=7)
    color_company_event: str | None = Field(None, max_length=7)

    @field_validator("weekly_off_rules", mode="before")
    @classmethod
    def validate_and_normalize_rules(cls, v: dict | None) -> dict | None:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("weekly_off_rules must be a JSON object or null")
        if len(v) == 0:
            return None  # Empty dict treated as null
        normalized: dict[str, list[int]] = {}
        for day, ordinals in v.items():
            day_upper = day.strip().upper()
            if day_upper not in _VALID_DAYS:
                raise ValueError(
                    f"Invalid day '{day}'. Must be one of: {', '.join(sorted(_VALID_DAYS))}"
                )
            if not isinstance(ordinals, list):
                raise ValueError(
                    f"Ordinals for '{day_upper}' must be an array of integers"
                )
            # Normalize: convert to int, deduplicate, sort
            clean: list[int] = []
            for o in ordinals:
                if not isinstance(o, (int, float)) or int(o) != o:
                    raise ValueError(
                        f"Ordinal '{o}' for '{day_upper}' must be an integer"
                    )
                val = int(o)
                if val < 1 or val > 5:
                    raise ValueError(
                        f"Ordinal {val} for '{day_upper}' must be between 1 and 5"
                    )
                clean.append(val)
            # Deduplicate and sort
            clean = sorted(set(clean))
            if clean:
                normalized[day_upper] = clean
        return normalized if normalized else None


def _auto_cleanup_rules(
    weekend_days: str | None,
    weekly_off_rules: dict | None,
) -> dict | None:
    """Remove any day from weekly_off_rules that is already a full weekend day.

    This ensures no stale rules remain when an admin moves a day to weekend_days.
    """
    if not weekly_off_rules or not weekend_days:
        return weekly_off_rules
    weekend_set = {d.strip().upper() for d in weekend_days.split(",")}
    cleaned = {
        day: ordinals
        for day, ordinals in weekly_off_rules.items()
        if day not in weekend_set
    }
    return cleaned if cleaned else None


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("CalendarSettings", "view"))],
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
    dependencies=[Depends(require_permission("CalendarSettings", "edit"))],
)
def update_settings(
    data: CalendarSettingsUpdate,
    db: Session = Depends(get_db),
):
    if data.office_start_time and not re.match(r'^\d{2}:\d{2}$', data.office_start_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="office_start_time must be in HH:MM format",
        )
    if data.office_end_time and not re.match(r'^\d{2}:\d{2}$', data.office_end_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="office_end_time must be in HH:MM format",
        )

    settings = db.scalar(select(CalendarSettings))
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar settings not configured",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Determine the effective weekend_days (from update or existing)
    effective_weekend = (
        update_data.get("weekend_days") or settings.weekend_days or ""
    )

    # Auto-cleanup: remove days from weekly_off_rules that are now weekend days
    if "weekly_off_rules" in update_data:
        update_data["weekly_off_rules"] = _auto_cleanup_rules(
            effective_weekend, update_data["weekly_off_rules"]
        )
    elif "weekend_days" in update_data and settings.weekly_off_rules:
        # Weekend days changed — clean up existing rules
        cleaned = _auto_cleanup_rules(
            effective_weekend, settings.weekly_off_rules
        )
        update_data["weekly_off_rules"] = cleaned

    for field, value in update_data.items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)

    return APIResponse(
        success=True,
        message="Calendar settings updated",
        data=CalendarSettingsResponse.model_validate(settings).model_dump(),
    )
