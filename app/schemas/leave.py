from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeaveTypeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=100)
    days_per_year: float = Field(0, ge=0, le=366)
    is_paid: bool = True
    is_carry_forward: bool = False
    max_carry_forward_days: float = Field(0, ge=0, le=366)
    requires_approval: bool = True
    requires_document: bool = False
    color: str = Field("#3B82F6", max_length=7)
    description: str | None = None


class LeaveTypeUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=10)
    name: str | None = Field(None, min_length=1, max_length=100)
    days_per_year: float | None = Field(None, ge=0, le=366)
    is_paid: bool | None = None
    is_carry_forward: bool | None = None
    max_carry_forward_days: float | None = Field(None, ge=0, le=366)
    requires_approval: bool | None = None
    requires_document: bool | None = None
    color: str | None = Field(None, max_length=7)
    description: str | None = None
    is_active: bool | None = None


class LeaveTypeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    days_per_year: float
    max_carry_forward_days: float
    is_paid: bool
    is_carry_forward: bool
    requires_approval: bool
    requires_document: bool
    is_active: bool
    color: str
    description: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class LeaveBalanceResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    leave_type_id: uuid.UUID
    leave_type_name: str | None = None
    leave_type_code: str | None = None
    year: int
    total_allowed: float
    used: float
    carried_forward: float
    remaining: float = 0

    model_config = ConfigDict(from_attributes=True)


class LeaveRequestCreate(BaseModel):
    leave_type_id: uuid.UUID
    from_date: date
    to_date: date
    reason: str | None = Field(None, max_length=1000)
    document_url: str | None = None
    is_half_day: bool = False
    half_day_session: Literal["FIRST_HALF", "SECOND_HALF"] | None = None

    @model_validator(mode="after")
    def check_dates(self) -> "LeaveRequestCreate":
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        if self.is_half_day:
            if self.from_date != self.to_date:
                raise ValueError("For half-day leaves, from_date and to_date must be the same date")
            if not self.half_day_session:
                raise ValueError("half_day_session is required when is_half_day is True")
        return self


class LeaveRequestUpdate(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class LeaveApprovalRequest(BaseModel):
    action: Literal["APPROVED", "REJECTED"]
    rejection_reason: str | None = Field(None, max_length=1000)
    hr_notes: str | None = Field(None, max_length=1000)


class LeaveRequestResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_code: str | None = None
    leave_type_id: uuid.UUID
    leave_type_name: str | None = None
    leave_type_code: str | None = None
    from_date: date
    to_date: date
    total_days: float
    reason: str | None = None
    status: str
    applied_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    hr_notes: str | None = None
    approval_steps: list[dict] | None = None
    document_url: str | None = None
    is_half_day: bool
    half_day_session: str | None = None

    model_config = ConfigDict(from_attributes=True)
