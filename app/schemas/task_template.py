import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TaskTemplateCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None


class TaskTemplateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    is_active: bool | None = None


class TaskTemplateResponse(BaseModel):
    id: uuid.UUID
    template_code: str
    title: str
    description: str | None = None
    is_active: bool
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskTemplateSearchItem(BaseModel):
    id: uuid.UUID
    template_code: str
    title: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
