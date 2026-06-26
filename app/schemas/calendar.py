from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, Field


# ── Shared Calendar Event Response (for FullCalendar frontend) ──


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start: str
    end: str | None = None
    allDay: bool = True
    backgroundColor: str = "#3B82F6"
    borderColor: str = "#3B82F6"
    textColor: str = "#ffffff"
    extendedProps: dict | None = None

    model_config = {"from_attributes": True}


# ── Company Event Schemas ──


VALID_EVENT_TYPES = {"COMPANY_EVENT"}
VALID_EVENT_SUBTYPES = {
    "ANNUAL_MEETING", "TRAINING", "CELEBRATION", "TOWN_HALL",
    "TEAM_BUILDING", "WORKSHOP", "OTHER",
}


class CompanyEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    event_subtype: str | None = None
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_all_day: bool = True
    color: str | None = "#8B5CF6"
    text_color: str | None = "#ffffff"


class CompanyEventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    event_subtype: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_all_day: bool | None = None
    color: str | None = None
    text_color: str | None = None
    is_active: bool | None = None


class CompanyEventResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    event_type: str
    event_subtype: str | None
    start_date: date
    end_date: date | None
    start_time: time | None
    end_time: time | None
    is_all_day: bool
    color: str | None
    text_color: str | None
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
