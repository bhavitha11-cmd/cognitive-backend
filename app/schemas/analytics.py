from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DashboardStats(BaseModel):
    total_clients: int = 0
    active_clients: int = 0
    total_projects: int = 0
    active_projects: int = 0
    completed_projects: int = 0
    total_tasks: int = 0
    pending_tasks: int = 0
    in_progress_tasks: int = 0
    completed_tasks: int = 0
    overdue_tasks: int = 0
    total_employees: int = 0
    active_employees: int = 0
    present_today: int = 0
    total_estimated_hours: float = 0
    total_actual_hours: float = 0
    overrun_percentage: float = 0.0


class PlanVsActualProject(BaseModel):
    id: UUID
    project_code: str
    name: str
    client_name: str | None = None
    status: str
    estimated_hours: float = 0
    actual_hours: float = 0
    overrun_hours: float = 0
    overrun_percentage: float = 0.0
    task_count: int = 0
    completed_task_count: int = 0
    planned_end_date: date | None = None


class PlanVsActualResponse(BaseModel):
    projects: list[PlanVsActualProject]
    total_estimated: float = 0
    total_actual: float = 0
    total_overrun: float = 0
    overall_overrun_pct: float = 0.0


class EmployeeUtilization(BaseModel):
    id: UUID
    employee_code: str
    employee_name: str
    department_name: str | None = None
    total_hours_logged: float = 0
    billable_hours: float = 0
    task_count: int = 0
    late_days: int = 0
    absence_days: int = 0
    utilization_percentage: float = 0.0


class UtilizationResponse(BaseModel):
    employees: list[EmployeeUtilization]
    period_start: date
    period_end: date
    total_hours_company: float = 0


class DepartmentLoad(BaseModel):
    department: str
    estimated_hours: float = 0
    actual_hours: float = 0
    task_count: int = 0
    overrun_percentage: float = 0.0


class DepartmentLoadResponse(BaseModel):
    departments: list[DepartmentLoad]


class OverdueTask(BaseModel):
    id: UUID
    task_code: str
    title: str
    project_id: UUID
    project_name: str
    status: str
    priority: str
    planned_delivery_date: date | None
    estimated_hours: float = 0
    actual_hours: float = 0
    days_overdue: int = 0
    assignee_name: str | None = None


class ClientPerformance(BaseModel):
    id: UUID
    name: str
    total_projects: int = 0
    active_projects: int = 0
    completed_projects: int = 0
    delayed_projects: int = 0
    total_estimated_hours: float = 0
    total_actual_hours: float = 0
    on_time_delivery_pct: float = 0.0


class ClientPerformanceResponse(BaseModel):
    clients: list[ClientPerformance]


class ScopeDistribution(BaseModel):
    scope_code: str | None = None
    scope_name: str | None = None
    department_category: str | None = None
    estimated_hours: float = 0
    actual_hours: float = 0
    task_count: int = 0


class ScopeDistributionResponse(BaseModel):
    scopes: list[ScopeDistribution]
