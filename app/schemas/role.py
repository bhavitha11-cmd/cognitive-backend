import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RoleBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Name of the role")
    description: str | None = Field(None, description="Detailed description of the role")
    parent_role_id: uuid.UUID | None = Field(None, description="UUID of the parent role it reports to")
    is_active: bool = Field(True, description="Active status of the role")


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    parent_role_id: uuid.UUID | None = None
    is_active: bool | None = None


class RoleResponse(RoleBase):
    id: uuid.UUID
    role_code: str
    hierarchy_level: int
    is_system_role: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


VALID_MODULES = {
    "HR", "Clients", "Finance", "Projects",
    "Inventory", "Settings", "Reports",
}

PERMISSION_ACTIONS = ["can_view", "can_create", "can_edit", "can_delete", "can_approve", "can_export"]


class RolePermissionItem(BaseModel):
    module_name: str = Field(..., description="Module name (e.g. Employees, Roles)")
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_approve: bool = False
    can_export: bool = False

    @classmethod
    def validate_module(cls, v: str) -> str:
        if v not in VALID_MODULES:
            raise ValueError(f"Invalid module '{v}'. Must be one of {VALID_MODULES}")
        return v


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
