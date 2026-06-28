from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


VALID_HOLIDAY_TYPES = {
    "PUBLIC", "COMPANY_SHUTDOWN", "SPECIAL", "OBSERVANCE",
    "OPTIONAL", "COMPANY_SPECIFIC",
}


class HolidayCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    date: date_type
    holiday_type: str = Field(default="PUBLIC")
    description: str | None = None
    affects_working_days: bool | None = True

    @field_validator("holiday_type")
    @classmethod
    def validate_holiday_type(cls, v: str) -> str:
        upper = v.upper()
        if upper not in VALID_HOLIDAY_TYPES:
            raise ValueError(f"Invalid holiday_type: {v}. Must be one of {VALID_HOLIDAY_TYPES}")
        return upper


class HolidayUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    date: date_type | None = None
    holiday_type: str | None = None
    description: str | None = None
    is_active: bool | None = None
    affects_working_days: bool | None = None

    @field_validator("holiday_type")
    @classmethod
    def validate_holiday_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        upper = v.upper()
        if upper not in VALID_HOLIDAY_TYPES:
            raise ValueError(f"Invalid holiday_type: {v}. Must be one of {VALID_HOLIDAY_TYPES}")
        return upper


class HolidayResponse(BaseModel):
    id: uuid.UUID
    name: str
    date: date_type
    holiday_type: str
    description: str | None
    is_active: bool
    affects_working_days: bool
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HolidayListResponse(BaseModel):
    id: uuid.UUID
    name: str
    date: date_type
    holiday_type: str
    description: str | None
    is_active: bool
    affects_working_days: bool

    model_config = {"from_attributes": True}
