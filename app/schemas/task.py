import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_TASK_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "CANCELLED"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_DEPT_CATS = {"CAD", "CAM", "GEN", "SALES", "ADMIN", "MKRT", "SUPRT"}


class TaskCreate(BaseModel):
    task_code: str = Field(min_length=1, max_length=100)
    project_id: uuid.UUID
    parent_task_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    scope_of_work_id: uuid.UUID | None = None
    department_category: str | None = None
    status: str = "NOT_STARTED"
    priority: str = "MEDIUM"
    estimated_hours: float = 0
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    received_date: date | None = None
    planned_delivery_date: date | None = None
    remarks: str | None = None

    @field_validator("department_category")
    @classmethod
    def validate_dept_cat(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_DEPT_CATS:
            raise ValueError(f"department_category must be one of {sorted(VALID_DEPT_CATS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_TASK_STATUSES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v


class TaskUpdate(BaseModel):
    task_code: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    parent_task_id: uuid.UUID | None = None
    scope_of_work_id: uuid.UUID | None = None
    department_category: str | None = None
    status: str | None = None
    priority: str | None = None
    estimated_hours: float | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    received_date: date | None = None
    planned_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    progress: float | None = None
    remarks: str | None = None
    is_active: bool | None = None

    @field_validator("department_category")
    @classmethod
    def validate_dept_cat(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_DEPT_CATS:
            raise ValueError(f"department_category must be one of {sorted(VALID_DEPT_CATS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_TASK_STATUSES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        return v


class TaskStatusUpdate(BaseModel):
    status: str
    progress: float | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_TASK_STATUSES)}")
        return v


class TaskAssignmentCreate(BaseModel):
    employee_id: uuid.UUID
    assigned_hours: float = 0
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    notes: str | None = None


class TaskAssignmentUpdate(BaseModel):
    assigned_hours: float | None = None
    status: str | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        valid = {"ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
        if v is not None and v not in valid:
            raise ValueError(f"status must be one of {sorted(valid)}")
        return v


class TaskAssignmentResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    employee_id: uuid.UUID | None
    employee_name: str | None = None
    employee_code: str | None = None
    assigned_by: uuid.UUID | None
    assigned_hours: float
    planned_start_date: date | None
    planned_end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    status: str
    assigned_at: datetime | None
    completed_at: datetime | None
    notes: str | None

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: uuid.UUID
    task_code: str
    title: str
    description: str | None
    project_id: uuid.UUID
    project_name: str | None = None
    parent_task_id: uuid.UUID | None
    scope_of_work_id: uuid.UUID | None
    scope_name: str | None = None
    department_category: str | None
    status: str
    priority: str
    estimated_hours: float
    actual_hours: float = 0.0
    planned_start_date: date | None
    planned_end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    received_date: date | None
    planned_delivery_date: date | None
    actual_delivery_date: date | None
    progress: float
    remarks: str | None
    is_active: bool
    assignments: list[TaskAssignmentResponse] = []
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    id: uuid.UUID
    task_code: str
    title: str
    project_id: uuid.UUID
    project_name: str | None = None
    department_category: str | None
    status: str
    priority: str
    estimated_hours: float
    actual_hours: float = 0.0
    progress: float
    planned_start_date: date | None
    planned_end_date: date | None
    planned_delivery_date: date | None
    actual_delivery_date: date | None
    assignee_count: int = 0

    model_config = ConfigDict(from_attributes=True)
