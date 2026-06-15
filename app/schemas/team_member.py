import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class TeamMemberCreate(BaseModel):
    employee_id: uuid.UUID
    role_in_team: Literal["LEAD", "MEMBER", "CO_LEAD"] = "MEMBER"
    is_primary_team: bool = False


class TeamMemberUpdate(BaseModel):
    role_in_team: Literal["LEAD", "MEMBER", "CO_LEAD"] | None = None
    is_primary_team: bool | None = None


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_code: str | None = None
    role_in_team: str
    is_primary_team: bool
    joined_at: datetime
    left_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
