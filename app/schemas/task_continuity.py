from __future__ import annotations

import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal, Optional


class TaskRiskResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    task_title: Optional[str] = None
    task_code: Optional[str] = None
    project_id: uuid.UUID
    project_name: Optional[str] = None
    assignment_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: Optional[str] = None
    leave_request_id: uuid.UUID
    leave_start_date: date
    leave_end_date: date
    remaining_hours: float
    risk_level: str
    days_impacted: int
    project_impact: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManagerDecisionCreate(BaseModel):
    decision: Literal["CONTINUE", "PAUSE", "REASSIGN", "SPLIT", "DELEGATE"]
    reassign_to_id: Optional[uuid.UUID] = Field(None, description="Employee ID to reassign or split to")
    delegate_id: Optional[uuid.UUID] = Field(None, description="Employee ID to delegate execution to")
    reason: Optional[str] = Field(None, description="Reason for the decision")
    pause_classification: Optional[Literal[
        "Waiting Customer", "Waiting Information", "Waiting Review", "Leave", "Blocked", "Dependency"
    ]] = Field(None, description="Classification of the pause reason")


class ManagerDecisionResponse(BaseModel):
    id: uuid.UUID
    task_risk_id: uuid.UUID
    task_id: uuid.UUID
    manager_id: Optional[uuid.UUID] = None
    decision: str
    details: Optional[dict] = None
    decided_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskDelegationResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    owner_id: uuid.UUID
    owner_name: Optional[str] = None
    delegate_id: uuid.UUID
    delegate_name: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    delegated_by: Optional[uuid.UUID] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskPauseHistoryResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    paused_at: datetime
    paused_by: Optional[uuid.UUID] = None
    resumed_at: Optional[datetime] = None
    resumed_by: Optional[uuid.UUID] = None
    reason: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TaskTransferHistoryResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    from_employee_id: Optional[uuid.UUID] = None
    from_employee_name: Optional[str] = None
    to_employee_id: Optional[uuid.UUID] = None
    to_employee_name: Optional[str] = None
    transfer_date: datetime
    remaining_hours: float
    reason: Optional[str] = None
    manager_id: Optional[uuid.UUID] = None
    transfer_type: str

    model_config = ConfigDict(from_attributes=True)


class ReassignmentWidgetRow(BaseModel):
    project_id: uuid.UUID
    project_name: str
    task_id: uuid.UUID
    task_code: str
    task_title: str
    employee_id: uuid.UUID
    employee_name: str
    remaining_hours: float
    days_remaining: int
    leave_duration: float
    suggested_impact: str


class ContinuityDashboardKPIs(BaseModel):
    employees_on_leave_with_active_tasks: int
    tasks_at_risk: int
    projects_at_risk: int
    upcoming_resource_shortage: int
    available_engineers_count: int
    overloaded_engineers_count: int
    resource_utilization_pct: float
    reassignment_trend: dict[str, int]
