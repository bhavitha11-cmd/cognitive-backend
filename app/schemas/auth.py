import uuid
from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str
    type: str = "access"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class PermissionDetail(BaseModel):
    module_name: str
    can_view: bool
    can_create: bool
    can_edit: bool
    can_delete: bool
    can_approve: bool
    can_export: bool


class UserMeResponse(BaseModel):
    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    email: str
    username: str
    is_active: bool
    roles: list[str]
    permissions: list[PermissionDetail]
