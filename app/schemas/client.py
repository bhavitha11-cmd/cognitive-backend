import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientCreate(BaseModel):
    client_code: str = Field("", min_length=0, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    industry: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=50)
    country: str | None = None
    address: str | None = None
    notes: str | None = None


class ClientUpdate(BaseModel):
    client_code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=200)
    industry: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=50)
    country: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class ClientResponse(BaseModel):
    id: uuid.UUID
    client_code: str
    name: str
    industry: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    country: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool
    project_count: int = 0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
