import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class TeamCreate(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=200)
    team_code: str = Field(..., min_length=1, max_length=50)
    description: str | None = Field(None, max_length=2000)
    department_id: uuid.UUID | None = None


class TeamUpdate(BaseModel):
    team_name: str | None = Field(None, min_length=1, max_length=200)
    team_code: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = Field(None, max_length=2000)
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


class TeamLookupItem(BaseModel):
    id: uuid.UUID
    team_name: str
    team_code: str
    department_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class TeamResponse(BaseModel):
    id: uuid.UUID
    team_name: str
    team_code: str
    description: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    member_count: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    team_lead_name: str | None = None
    team_lead_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)
