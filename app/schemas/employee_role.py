import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EmployeeRoleCreate(BaseModel):
    employee_id: uuid.UUID
    role_id: uuid.UUID


class EmployeeRoleResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    role_id: uuid.UUID
    assigned_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
