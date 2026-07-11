from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApprovalWorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    module_type: str = Field(..., min_length=1, max_length=50)
    approval_strategy: str = Field("ANY_ONE", max_length=50)

    @field_validator("approval_strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"ANY_ONE", "ALL", "FIRST_ASSIGNED", "ROUND_ROBIN"}
        if v not in allowed:
            raise ValueError(f"approval_strategy must be one of {allowed}")
        return v


class ApprovalWorkflowUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    approval_strategy: str | None = Field(None, max_length=50)
    is_active: bool | None = None

    @field_validator("approval_strategy")
    @classmethod
    def validate_strategy(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"ANY_ONE", "ALL", "FIRST_ASSIGNED", "ROUND_ROBIN"}
        if v not in allowed:
            raise ValueError(f"approval_strategy must be one of {allowed}")
        return v


class ApprovalWorkflowStepCreate(BaseModel):
    requester_role_id: uuid.UUID
    level: int = Field(..., ge=1)
    approver_role_id: uuid.UUID
    resolution_scope: str = Field(..., max_length=50)

    @field_validator("resolution_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        allowed = {"REPORTING_HIERARCHY", "TEAM_ASSIGNMENT", "DEPARTMENT_ASSIGNMENT", "GLOBAL"}
        if v not in allowed:
            raise ValueError(f"resolution_scope must be one of {allowed}")
        return v


class ApprovalWorkflowStepResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    requester_role_id: uuid.UUID
    requester_role_name: str | None = None
    level: int
    approver_role_id: uuid.UUID
    approver_role_name: str | None = None
    resolution_scope: str

    model_config = ConfigDict(from_attributes=True)


class ApprovalWorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    module_type: str
    version: int
    approval_strategy: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    steps: list[ApprovalWorkflowStepResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ApprovalInstanceResponse(BaseModel):
    id: uuid.UUID
    module_type: str
    target_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version: int
    level: int
    approver_role_id: uuid.UUID
    approver_role_name: str | None = None
    assigned_approver_id: uuid.UUID | None = None
    assigned_approver_name: str | None = None
    status: str
    actioned_by_id: uuid.UUID | None = None
    actioned_by_name: str | None = None
    actioned_at: datetime | None = None
    comments: str | None = None

    # Audit fields
    resolved_by_scope: str | None = None
    resolved_approver_id: uuid.UUID | None = None
    resolved_approver_name: str | None = None
    resolution_time: datetime | None = None

    # Target info for UI
    requester_name: str | None = None
    requester_code: str | None = None
    details_summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalActionRequest(BaseModel):
    action: Literal["APPROVED", "REJECTED"]
    comments: str | None = Field(None, max_length=1000)
