import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


VALID_MODULES = {
    "HR", "Clients", "Finance", "Projects",
    "Inventory", "Settings", "Reports", "Timesheets", "Tasks",
    "Attendance", "Leave", "Analytics",
    "Holiday", "Calendar", "CompanyEvent", "Dashboard", "CalendarSettings",
    "TaskTemplate",
}

VALID_ACCESS_LEVELS = {"FULL", "MANAGED", "TEAM", "SELF"}

PERMISSION_ACTIONS = ["can_view", "can_create", "can_edit", "can_delete", "can_approve", "can_export"]


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


class RolePermissionItem(BaseModel):
    module_name: str = Field(..., description="Module name")
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_approve: bool = False
    can_export: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("module_name")
    @classmethod
    def validate_module(cls, v: str) -> str:
        if v not in VALID_MODULES:
            raise ValueError(f"Invalid module '{v}'. Must be one of {sorted(VALID_MODULES)}")
        return v


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
    can_delete: bool
    can_approve: bool
    can_export: bool

    model_config = ConfigDict(from_attributes=True)
