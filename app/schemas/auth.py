import uuid
from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


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
