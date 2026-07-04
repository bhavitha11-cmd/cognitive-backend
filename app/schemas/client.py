import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdditionalContactSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=200)
    phone: str = Field(..., min_length=1, max_length=50)


class ClientCreate(BaseModel):
    client_code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    industry: str | None = Field(None, max_length=200)
    contact_person: str = Field(..., min_length=1, max_length=200)
    contact_email: EmailStr = Field(...)
    contact_phone: str = Field(..., min_length=1, max_length=50)
    alternate_phone: str | None = Field(None, max_length=50)
    additional_contacts: list[AdditionalContactSchema] | None = Field(default_factory=list)
    country: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1, max_length=1000)
    notes: str | None = Field(None, max_length=5000)


class ClientUpdate(BaseModel):
    client_code: str | None = Field(None, min_length=1, max_length=20)
    name: str | None = Field(None, min_length=1, max_length=200)
    industry: str | None = Field(None, max_length=200)
    contact_person: str | None = Field(None, min_length=1, max_length=200)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, min_length=1, max_length=50)
    alternate_phone: str | None = Field(None, max_length=50)
    additional_contacts: list[AdditionalContactSchema] | None = None
    country: str | None = Field(None, min_length=1, max_length=100)
    address: str | None = Field(None, min_length=1, max_length=1000)
    notes: str | None = Field(None, max_length=5000)
    is_active: bool | None = None
    status: Optional[Literal["Active", "Inactive"]] = None
    deactivation_reason: str | None = Field(None, max_length=1000)


class ClientLookupItem(BaseModel):
    id: uuid.UUID
    name: str
    client_code: str

    model_config = ConfigDict(from_attributes=True)


class ClientResponse(BaseModel):
    id: uuid.UUID
    client_code: str
    name: str
    industry: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    alternate_phone: str | None = None
    additional_contacts: list[AdditionalContactSchema] | None = None
    country: str | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool
    status: str
    deactivation_reason: str | None = None
    deactivated_at: datetime | None = None
    deactivated_by: str | None = None
    project_count: int = 0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
