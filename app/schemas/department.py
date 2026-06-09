import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=20)
    description: str | None = None
    department_head_id: uuid.UUID | None = None
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    code: str | None = Field(None, min_length=2, max_length=20)
    description: str | None = None
    department_head_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    department_head_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    employee_count: int = 0
    department_head_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

