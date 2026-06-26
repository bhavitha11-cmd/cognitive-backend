import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_STATUSES = {"Yet To Start", "In Progress", "Completed", "Cancelled", "On Hold"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_INVOICE_STATUSES = {"PENDING", "INVOICED", "PARTIALLY_INVOICED", "NOT_APPLICABLE"}
VALID_FEEDBACK_STATUSES = {"PENDING", "RECEIVED", "POSITIVE", "NEGATIVE", "NA"}


class ProjectCreate(BaseModel):
    part_number: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=3, max_length=500)
    part_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    client_id: uuid.UUID
    project_manager_id: uuid.UUID | None = None
    department_id: uuid.UUID
    status: str = "Yet To Start"
    priority: str = "MEDIUM"
    is_billable: bool = True
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    estimated_hours: float = 0
    contract_hours: float | None = None
    invoice_status: str = "PENDING"
    tok_form: str | None = None
    feedback_status: str = "PENDING"
    status_reason: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("invoice_status")
    @classmethod
    def validate_invoice_status(cls, v: str) -> str:
        if v not in VALID_INVOICE_STATUSES:
            raise ValueError(f"invoice_status must be one of {sorted(VALID_INVOICE_STATUSES)}")
        return v

    @field_validator("feedback_status")
    @classmethod
    def validate_feedback_status(cls, v: str) -> str:
        if v not in VALID_FEEDBACK_STATUSES:
            raise ValueError(f"feedback_status must be one of {sorted(VALID_FEEDBACK_STATUSES)}")
        return v


class ProjectUpdate(BaseModel):
    part_number: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=3, max_length=500)
    part_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    client_id: uuid.UUID | None = None
    project_manager_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    # NOTE: status, actual_start_date, actual_end_date, estimated_hours
    # are system-managed and cannot be set manually via API update.
    priority: str | None = None
    is_billable: bool | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    contract_hours: float | None = None
    invoice_status: str | None = None
    tok_form: str | None = None
    feedback_status: str | None = None
    status_reason: str | None = None
    is_active: bool | None = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("invoice_status")
    @classmethod
    def validate_invoice_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_INVOICE_STATUSES:
            raise ValueError(f"invoice_status must be one of {sorted(VALID_INVOICE_STATUSES)}")
        return v

    @field_validator("feedback_status")
    @classmethod
    def validate_feedback_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FEEDBACK_STATUSES:
            raise ValueError(f"feedback_status must be one of {sorted(VALID_FEEDBACK_STATUSES)}")
        return v


class ProjectResponse(BaseModel):
    id: uuid.UUID
    part_number: str
    name: str
    part_name: str
    description: str | None = None
    client_id: uuid.UUID
    client_name: str | None = None
    project_manager_id: uuid.UUID | None = None
    project_manager_name: str | None = None
    department_id: uuid.UUID
    department_name: str | None = None
    department_code: str | None = None
    status: str
    priority: str
    is_billable: bool
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    estimated_hours: float
    contract_hours: float | None = None
    invoice_status: str
    tok_form: str | None = None
    feedback_status: str
    status_reason: str | None = None
    is_active: bool
    task_count: int = 0
    completed_task_count: int = 0
    actual_hours: float = 0.0
    progress: float = 0.0          # hour-weighted completion %, auto-calculated
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Project Member schemas ─────────────────────────────────────────────────────

VALID_MEMBER_ROLES = {"ENGINEER", "LEAD", "CO_LEAD", "REVIEWER", "OBSERVER"}


class ProjectMemberAdd(BaseModel):
    employee_id: uuid.UUID
    role: str = "ENGINEER"
    allocation_pct: int = Field(default=100, ge=1, le=100)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_MEMBER_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_MEMBER_ROLES)}")
        return v


class ProjectMemberResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    role: str
    allocation_pct: int
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)
