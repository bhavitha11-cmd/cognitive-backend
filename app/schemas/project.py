import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_STATUSES = {"DRAFT", "ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_BILLING_TYPES = {"FIXED", "TIME_AND_MATERIAL", "RETAINER", "INTERNAL"}
VALID_INVOICE_STATUSES = {"PENDING", "INVOICED", "PARTIALLY_INVOICED", "NOT_APPLICABLE"}
VALID_FEEDBACK_STATUSES = {"PENDING", "RECEIVED", "POSITIVE", "NEGATIVE", "NA"}


class ProjectCreate(BaseModel):
    project_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    client_id: uuid.UUID
    project_manager_id: uuid.UUID | None = None
    status: str = "DRAFT"
    priority: str = "MEDIUM"
    billing_type: str = "FIXED"
    is_billable: bool = True
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    estimated_hours: float = 0
    contract_hours: float | None = None
    invoice_status: str = "PENDING"
    tok_form: str | None = None
    feedback_status: str = "PENDING"

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

    @field_validator("billing_type")
    @classmethod
    def validate_billing_type(cls, v: str) -> str:
        if v not in VALID_BILLING_TYPES:
            raise ValueError(f"billing_type must be one of {sorted(VALID_BILLING_TYPES)}")
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
    project_code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    client_id: uuid.UUID | None = None
    project_manager_id: uuid.UUID | None = None
    status: str | None = None
    priority: str | None = None
    billing_type: str | None = None
    is_billable: bool | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    estimated_hours: float | None = None
    contract_hours: float | None = None
    invoice_status: str | None = None
    tok_form: str | None = None
    feedback_status: str | None = None
    is_active: bool | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("billing_type")
    @classmethod
    def validate_billing_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_BILLING_TYPES:
            raise ValueError(f"billing_type must be one of {sorted(VALID_BILLING_TYPES)}")
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
    project_code: str
    name: str
    description: str | None = None
    client_id: uuid.UUID
    client_name: str | None = None
    project_manager_id: uuid.UUID | None = None
    project_manager_name: str | None = None
    status: str
    priority: str
    billing_type: str
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
    is_active: bool
    task_count: int = 0
    completed_task_count: int = 0
    actual_hours: float = 0.0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
