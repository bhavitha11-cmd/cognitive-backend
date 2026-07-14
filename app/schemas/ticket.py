import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

# ── Ticket Category Schemas ────────────────────────────────────────────────────
class TicketCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True

class TicketCategoryCreate(TicketCategoryBase):
    pass

class TicketCategoryResponse(TicketCategoryBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Type Schemas ────────────────────────────────────────────────────────
class TicketTypeBase(BaseModel):
    category_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True

class TicketTypeCreate(TicketTypeBase):
    pass

class TicketTypeResponse(TicketTypeBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Priority Schemas ────────────────────────────────────────────────────
class TicketPriorityResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Status Schemas ──────────────────────────────────────────────────────
class TicketStatusResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Category Handler Schemas ─────────────────────────────────────────────
class TicketCategoryHandlerCreate(BaseModel):
    category_id: uuid.UUID
    employee_id: uuid.UUID

class TicketCategoryHandlerResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Attachment Schemas ──────────────────────────────────────────────────
class TicketAttachmentCreate(BaseModel):
    filename: str
    file_url: str

class TicketAttachmentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    file_url: str
    uploaded_by_id: uuid.UUID | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Comment Schemas ─────────────────────────────────────────────────────
class TicketCommentCreate(BaseModel):
    comment: str = Field(..., min_length=1)

class TicketCommentResponse(BaseModel):
    id: uuid.UUID
    comment: str
    commented_by_id: uuid.UUID
    commented_by_name: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket History Schemas ─────────────────────────────────────────────────────
class TicketHistoryResponse(BaseModel):
    id: uuid.UUID
    action: str
    field_name: str | None = None
    previous_value: str | None = None
    new_value: str | None = None
    performed_by_id: uuid.UUID
    performed_by_name: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ── Ticket Schemas ─────────────────────────────────────────────────────────────
class TicketCreate(BaseModel):
    category_id: uuid.UUID
    ticket_type_id: uuid.UUID
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority_id: uuid.UUID
    attachments: list[TicketAttachmentCreate] | None = Field(default_factory=list)

class TicketResponse(BaseModel):
    id: uuid.UUID
    ticket_number: str
    category_id: uuid.UUID
    category_name: str | None = None
    ticket_type_id: uuid.UUID
    ticket_type_name: str | None = None
    subject: str
    description: str
    priority_id: uuid.UUID
    priority_name: str | None = None
    status_id: uuid.UUID
    status_name: str | None = None
    raised_by_id: uuid.UUID
    raised_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TicketDetailResponse(TicketResponse):
    attachments: list[TicketAttachmentResponse] = Field(default_factory=list)
    comments: list[TicketCommentResponse] = Field(default_factory=list)
    history: list[TicketHistoryResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)
