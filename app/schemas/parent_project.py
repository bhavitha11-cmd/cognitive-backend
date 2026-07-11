import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.project import ProjectCreate, ProjectResponse


class ParentProjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=500)
    description: str | None = Field(None, max_length=5000)
    client_id: uuid.UUID
    project_manager_id: uuid.UUID | None = None
    department_id: uuid.UUID
    parts: List[ProjectCreate] = []


class ParentProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=500)
    description: str | None = Field(None, max_length=5000)
    client_id: uuid.UUID | None = None
    project_manager_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


class ParentProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    client_id: uuid.UUID
    client_name: str | None = None
    project_manager_id: uuid.UUID | None = None
    project_manager_name: str | None = None
    department_id: uuid.UUID
    department_name: str | None = None
    department_code: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Rolled-up metrics
    part_count: int = 0
    status: str = "Yet To Start"
    progress: float = 0.0
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    estimated_hours: float = 0.0
    actual_hours: float = 0.0

    # Associated Parts
    parts: List[ProjectResponse] = []

    model_config = ConfigDict(from_attributes=True)
