from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    """Base model that serializes field names as camelCase JSON keys."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --- Common Schemas ---
class SimpleProjectInfo(_CamelModel):
    id: UUID
    project_code: str
    name: str
    status: str
    progress: float
    planned_end_date: date | None = None
    actual_hours: float = 0.0
    estimated_hours: float = 0.0

class SimpleTaskInfo(_CamelModel):
    id: UUID
    task_code: str
    title: str
    status: str
    priority: str
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    planned_delivery_date: date | None = None
    assignee_name: str | None = None

# --- Executive Dashboard Schemas ---
class ExecutiveSummary(_CamelModel):
    total_projects: int = 0
    active_projects: int = 0
    completed_projects: int = 0
    delayed_projects: int = 0
    planned_hours: float = 0.0
    actual_hours: float = 0.0
    remaining_hours: float = 0.0
    company_utilization_percentage: float = 0.0
    employees_working_today: int = 0
    pending_timesheets_count: int = 0

class DepartmentPerf(_CamelModel):
    department_name: str
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    task_count: int = 0

class ProjectStatusCount(_CamelModel):
    status: str
    count: int

class BurnTrendPoint(_CamelModel):
    date: date
    hours_logged: float

class EmployeeUtilPoint(_CamelModel):
    employee_id: UUID
    employee_name: str
    utilization_percentage: float

class ExecutiveCharts(_CamelModel):
    project_statuses: list[ProjectStatusCount] = []
    department_performances: list[DepartmentPerf] = []
    planned_vs_actual: list[dict] = []
    hours_burn_trend: list[BurnTrendPoint] = []
    employee_utilization: list[EmployeeUtilPoint] = []

class DashboardAlert(_CamelModel):
    id: str
    level: str  # info, warning, error
    type: str   # project_overrun, project_delivery, timesheet_missing, workload_high
    message: str
    reference_id: UUID | None = None

class ExecutiveAlerts(_CamelModel):
    alerts: list[DashboardAlert] = []

class RecentActivity(_CamelModel):
    id: UUID
    action: str
    performed_by_name: str
    entity_type: str
    entity_code: str
    timestamp: datetime

class ExecutiveRecentActivities(_CamelModel):
    activities: list[RecentActivity] = []

# --- Project Dashboard Schemas ---
class ProjectSummary(_CamelModel):
    id: UUID
    project_code: str
    name: str
    customer_name: str | None = None
    department_name: str | None = None
    project_manager_name: str | None = None
    planned_hours: float = 0.0
    actual_hours: float = 0.0
    remaining_hours: float = 0.0
    completion_percentage: float = 0.0
    delivery_date: date | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0

class BurnCurvePoint(_CamelModel):
    date: date
    planned_cumulative_hours: float = 0.0
    actual_cumulative_hours: float = 0.0

class DailyProgressPoint(_CamelModel):
    date: date
    hours_logged: float = 0.0

class TaskTimeSummary(_CamelModel):
    id: UUID
    task_code: str
    title: str
    actual_hours: float = 0.0
    estimated_hours: float = 0.0

class ProjectCharts(_CamelModel):
    task_statuses: list[dict] = []
    burn_curve: list[BurnCurvePoint] = []
    daily_progress: list[DailyProgressPoint] = []
    top_time_consuming_tasks: list[TaskTimeSummary] = []

# --- Team Leader Dashboard Schemas ---
class TeamMemberAttendance(_CamelModel):
    employee_id: UUID
    employee_name: str
    status: str  # PRESENT, ABSENT, LEAVE
    clock_in: datetime | None = None
    clock_out: datetime | None = None

class TeamLeadSummary(_CamelModel):
    total_team_members: int = 0
    today_attendance_count: int = 0
    pending_approvals_count: int = 0
    tasks_in_progress_count: int = 0
    delayed_tasks_count: int = 0
    overloaded_employees_count: int = 0
    underutilized_employees_count: int = 0

class TeamWorkloadPoint(_CamelModel):
    employee_id: UUID
    employee_name: str
    assigned_hours: float
    available_hours: float
    utilization_percentage: float

class TeamLeadCharts(_CamelModel):
    employee_workload: list[TeamWorkloadPoint] = []
    employee_productivity: list[dict] = []
    task_completions_weekly: list[dict] = []
    timesheet_compliance: list[dict] = []

# --- Employee Dashboard Schemas ---
class EmployeeSummary(_CamelModel):
    today_tasks_count: int = 0
    upcoming_tasks_count: int = 0
    completed_tasks_count: int = 0
    pending_tasks_count: int = 0
    today_hours: float = 0.0
    weekly_hours: float = 0.0
    monthly_hours: float = 0.0
    remaining_hours: float = 0.0
    personal_productivity_percentage: float = 0.0

class EmployeeCharts(_CamelModel):
    daily_hours: list[dict] = []
    weekly_trend: list[dict] = []
    hours_distribution_by_project: list[dict] = []
    timesheet_status_summary: list[dict] = []

# --- Employee Performance Dashboard Schemas ---
class EmployeePerformanceRow(_CamelModel):
    employee_id: UUID
    employee_code: str
    employee_name: str
    department_name: str | None = None
    team_name: str | None = None
    utilization_percentage: float = 0.0
    planned_hours: float = 0.0
    actual_hours: float = 0.0
    variance_hours: float = 0.0
    task_completion_percentage: float = 0.0
    average_hours_per_task: float = 0.0
    average_delay_days: float = 0.0
    rework_hours: float = 0.0
    productivity_score: float = 0.0
    efficiency_score: float = 0.0
    timesheet_compliance_score: float = 0.0
    performance_rank: int = 0

class PerformanceRankingsResponse(_CamelModel):
    rankings: list[EmployeePerformanceRow] = []
