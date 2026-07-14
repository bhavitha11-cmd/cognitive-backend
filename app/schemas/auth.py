import uuid
from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: str
    type: str = "access"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


# ── Legacy boolean-based permission detail (backward compat) ──────────────────

class PermissionDetail(BaseModel):
    module_name: str
    can_view: bool
    can_create: bool
    can_edit: bool
    can_activate: bool


# ── New scope-based permission detail for /auth/me ────────────────────────────

class FeaturePermissionDetail(BaseModel):
    """Scope-based permission returned in /auth/me for the frontend sidebar
    and permission checks."""
    feature_key: str
    feature_name: str
    module_key: str
    module_name: str
    route: str | None = None
    menu_visible: bool = True
    view_scope: str = "NONE"
    create_scope: str = "NONE"
    update_scope: str = "NONE"
    delete_scope: str = "NONE"


class ModulePermissionDetail(BaseModel):
    """Module with its features and their scopes — for sidebar generation."""
    module_key: str
    module_name: str
    icon: str | None = None
    display_order: int
    features: list[FeaturePermissionDetail] = []


class UserMeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID | None = None  # alias for id, explicit for frontend
    employee_code: str
    first_name: str
    last_name: str
    email: str
    username: str
    is_active: bool
    must_change_password: bool = True
    roles: list[str]
    role_codes: list[str] = []
    data_access_level: str = "SELF"
    permissions: list[PermissionDetail]
    # New: scope-based permissions grouped by module for sidebar + matrix
    module_permissions: list[ModulePermissionDetail] = []
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
