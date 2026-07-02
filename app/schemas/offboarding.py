from __future__ import annotations

import uuid
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class OffboardImpactItem(BaseModel):
    id: str
    name: str
    detail: str | None = None


class OffboardImpactCategory(BaseModel):
    count: int
    items: List[OffboardImpactItem]


class OffboardImpactWarning(BaseModel):
    severity: Literal["info", "warning", "error"]
    message: str


class OffboardImpactResponse(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    current_status: str
    direct_reports: OffboardImpactCategory
    teams_led: OffboardImpactCategory
    departments_headed: OffboardImpactCategory
    projects_as_pm: OffboardImpactCategory
    active_tasks: OffboardImpactCategory
    pending_leaves: OffboardImpactCategory
    pending_time_entries: OffboardImpactCategory
    project_memberships: OffboardImpactCategory
    warnings: List[OffboardImpactWarning]


class TaskReassignment(BaseModel):
    task_id: str
    new_assignee_id: str


class ProjectPMReassignment(BaseModel):
    project_id: str
    new_pm_id: str


class OffboardExecuteRequest(BaseModel):
    effective_date: date
    final_status: Literal["RESIGNED", "TERMINATED"] = "RESIGNED"
    reason: Optional[str] = Field(None, max_length=500)

    new_manager_id: Optional[str] = None
    direct_report_ids: List[str] = Field(default_factory=list)

    new_team_lead_id: Optional[str] = None
    team_ids: List[str] = Field(default_factory=list)

    new_dept_head_id: Optional[str] = None
    department_ids: List[str] = Field(default_factory=list)

    project_pm_reassignments: List[ProjectPMReassignment] = Field(default_factory=list)
    task_reassignments: List[TaskReassignment] = Field(default_factory=list)
    bulk_task_reassign_to: Optional[str] = None

    leave_disposition: Literal["CANCEL_ALL", "KEEP"] = "CANCEL_ALL"
    time_entry_disposition: Literal["AUTO_APPROVE", "AUTO_REJECT", "KEEP"] = "KEEP"


class OffboardExecuteResponse(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    final_status: str
    effective_date: date
    event_id: uuid.UUID
    transfers_completed: dict
