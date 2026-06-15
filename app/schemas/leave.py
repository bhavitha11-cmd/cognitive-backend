from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeaveTypeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=10)
    name: str = Field(..., min_length=1, max_length=100)
    days_per_year: float = 0
    is_paid: bool = True
    is_carry_forward: bool = False
    max_carry_forward_days: float = 0
    requires_approval: bool = True
    color: str = "#3B82F6"
    description: str | None = None


class LeaveTypeUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=10)
    name: str | None = Field(None, min_length=1, max_length=100)
    days_per_year: float | None = None
    is_paid: bool | None = None
    is_carry_forward: bool | None = None
    max_carry_forward_days: float | None = None
    requires_approval: bool | None = None
    color: str | None = None
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
    reason: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> "LeaveRequestCreate":
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        return self


class LeaveRequestUpdate(BaseModel):
    reason: str | None = None


class LeaveApprovalRequest(BaseModel):
    action: str = Field(..., description="APPROVED or REJECTED")
    rejection_reason: str | None = None
    hr_notes: str | None = None


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

    model_config = ConfigDict(from_attributes=True)
