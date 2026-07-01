import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class DesignationCreate(BaseModel):
    department_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=20)
    level: int = Field(1, ge=1, le=100)
    description: str | None = Field(None, max_length=2000)
    is_active: bool = True


class DesignationUpdate(BaseModel):
    department_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=2, max_length=100)
    code: str | None = Field(None, min_length=2, max_length=20)
    level: int | None = Field(None, ge=1, le=100)
    description: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class DesignationResponse(BaseModel):
    id: uuid.UUID
    department_id: uuid.UUID
    name: str
    code: str
    level: int
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    employee_count: int = 0
    department_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

