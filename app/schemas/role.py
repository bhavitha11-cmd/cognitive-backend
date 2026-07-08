import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from app.core.permission_scope import PermissionScope


# ── Legacy constants (kept for backward-compatibility in old seeders) ─────────

VALID_MODULES = {
    "HR", "Clients", "Finance", "Projects",
    "Inventory", "Settings", "Reports", "Timesheets", "Tasks",
    "Attendance", "Leave", "Analytics",
    "Holiday", "Calendar", "CompanyEvent", "Dashboard", "CalendarSettings",
    "TaskTemplate",
}

VALID_ACCESS_LEVELS = {"FULL", "MANAGED", "TEAM", "SELF"}

PERMISSION_ACTIONS = ["can_view", "can_create", "can_edit", "can_activate"]


# ── Role CRUD Schemas ────────────────────────────────────────────────────────

class RoleBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    parent_role_id: uuid.UUID | None = None
    is_active: bool = True
    data_access_level: str = Field("SELF", description="Row-level data visibility: FULL, MANAGED, TEAM, SELF")

    @field_validator("data_access_level")
    @classmethod
    def validate_access_level(cls, v: str) -> str:
        if v not in VALID_ACCESS_LEVELS:
            raise ValueError(f"Invalid access level '{v}'. Must be one of {sorted(VALID_ACCESS_LEVELS)}")
        return v


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=500)
    parent_role_id: uuid.UUID | None = None
    is_active: bool | None = None
    data_access_level: str | None = Field(None, description="Row-level data visibility: FULL, MANAGED, TEAM, SELF")

    @field_validator("data_access_level")
    @classmethod
    def validate_access_level(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ACCESS_LEVELS:
            raise ValueError(f"Invalid access level '{v}'. Must be one of {sorted(VALID_ACCESS_LEVELS)}")
        return v


# ── Legacy Boolean-based Permission Item (backward compat for old endpoints) ─

class RolePermissionItem(BaseModel):
    module_name: str = Field(..., description="Module name")
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_activate: bool = False

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def resolve_module_name(cls, data: any) -> any:
        if isinstance(data, dict):
            if not data.get("module_name") and data.get("feature"):
                feat = data.get("feature")
                if isinstance(feat, dict):
                    data["module_name"] = feat.get("feature_name") or feat.get("feature_key")
            return data
        
        m_name = getattr(data, "module_name", None)
        if not m_name:
            feature = getattr(data, "feature", None)
            if feature:
                m_name = feature.feature_name or feature.feature_key
            else:
                m_name = "Unknown"
        
        return {
            "module_name": m_name,
            "can_view": getattr(data, "can_view", False),
            "can_create": getattr(data, "can_create", False),
            "can_edit": getattr(data, "can_edit", False),
            "can_activate": getattr(data, "can_activate", False),
        }


# ── New Scope-based Permission Schemas ────────────────────────────────────────

class FeaturePermissionItem(BaseModel):
    """One row in the permission matrix: a feature + four scope values."""
    feature_id: uuid.UUID
    feature_key: str
    view_scope: str = PermissionScope.NONE.value
    create_scope: str = PermissionScope.NONE.value
    update_scope: str = PermissionScope.NONE.value
    delete_scope: str = PermissionScope.NONE.value

    model_config = ConfigDict(from_attributes=True)

    @field_validator("view_scope", "create_scope", "update_scope", "delete_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in PermissionScope.choices():
            raise ValueError(f"Invalid scope '{v}'. Must be one of {PermissionScope.choices()}")
        return v


class FeaturePermissionUpdate(BaseModel):
    """Input schema for setting/updating a single feature's permission scopes."""
    feature_id: uuid.UUID
    view_scope: str = PermissionScope.NONE.value
    create_scope: str = PermissionScope.NONE.value
    update_scope: str = PermissionScope.NONE.value
    delete_scope: str = PermissionScope.NONE.value

    @field_validator("view_scope", "create_scope", "update_scope", "delete_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v not in PermissionScope.choices():
            raise ValueError(f"Invalid scope '{v}'. Must be one of {PermissionScope.choices()}")
        return v


class FeaturePermissionBulkUpdate(BaseModel):
    """Input schema for bulk-updating a role's permissions (the full matrix)."""
    permissions: list[FeaturePermissionUpdate]


class ClonePermissionsRequest(BaseModel):
    """Clone all permissions from a source role to the target role."""
    source_role_id: uuid.UUID


# ── Module & Feature response schemas ─────────────────────────────────────────

class FeatureResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    feature_key: str
    feature_name: str
    description: str | None = None
    route: str | None = None
    icon: str | None = None
    display_order: int
    menu_visible: bool
    permission_enabled: bool
    is_system: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ModuleResponse(BaseModel):
    id: uuid.UUID
    module_key: str
    module_name: str
    display_order: int
    icon: str | None = None
    is_active: bool
    features: list[FeatureResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ── Role Response (updated with scope-based permissions) ──────────────────────

class RolePermissionScopeResponse(BaseModel):
    """Permission response with scope values for the new UI."""
    id: uuid.UUID
    feature_id: uuid.UUID
    feature_key: str
    feature_name: str
    module_key: str
    module_name: str
    view_scope: str
    create_scope: str
    update_scope: str
    delete_scope: str

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(RoleBase):
    id: uuid.UUID
    role_code: str
    hierarchy_level: int
    is_system_role: bool
    is_super_admin: bool = False
    data_access_level: str = "SELF"
    created_at: datetime
    updated_at: datetime
    permissions: list[RolePermissionItem] = []

    model_config = ConfigDict(from_attributes=True)


class RolePermissionList(BaseModel):
    permissions: list[RolePermissionItem]


class RolePermissionResponse(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    module_name: str
    can_view: bool
    can_create: bool
    can_edit: bool
    can_activate: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def resolve_module_name(cls, data: any) -> any:
        if isinstance(data, dict):
            if not data.get("module_name") and data.get("feature"):
                feat = data.get("feature")
                if isinstance(feat, dict):
                    data["module_name"] = feat.get("feature_name") or feat.get("feature_key")
            return data
        
        m_name = getattr(data, "module_name", None)
        if not m_name:
            feature = getattr(data, "feature", None)
            if feature:
                m_name = feature.feature_name or feature.feature_key
            else:
                m_name = "Unknown"
        
        return {
            "id": getattr(data, "id", None),
            "role_id": getattr(data, "role_id", None),
            "module_name": m_name,
            "can_view": getattr(data, "can_view", False),
            "can_create": getattr(data, "can_create", False),
            "can_edit": getattr(data, "can_edit", False),
            "can_activate": getattr(data, "can_activate", False),
        }
