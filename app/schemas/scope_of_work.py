import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_DEPT_CATEGORIES = {"CAD", "CAM", "GEN", "SALES", "ADMIN", "MKRT", "SUPRT"}


class ScopeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    department_category: str
    description: str | None = None

    @field_validator("department_category")
    @classmethod
    def validate_department_category(cls, v: str) -> str:
        if v not in VALID_DEPT_CATEGORIES:
            raise ValueError(
                f"department_category must be one of: {', '.join(sorted(VALID_DEPT_CATEGORIES))}"
            )
        return v


class ScopeUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=200)
    department_category: str | None = None
    description: str | None = None
    is_active: bool | None = None

    @field_validator("department_category")
    @classmethod
    def validate_department_category(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_DEPT_CATEGORIES:
            raise ValueError(
                f"department_category must be one of: {', '.join(sorted(VALID_DEPT_CATEGORIES))}"
            )
        return v


class ScopeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    department_category: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
