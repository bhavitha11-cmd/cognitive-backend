import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EmployeeScheduleCreate(BaseModel):
    employee_id: uuid.UUID
    week_start_date: date
    available_hours: float = 40.0


class EmployeeScheduleUpdate(BaseModel):
    available_hours: float | None = None


class EmployeeScheduleResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_code: str | None = None
    week_start_date: date
    available_hours: float
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TaskDependencyCreate(BaseModel):
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    dependency_type: str = "FINISH_TO_START"


class TaskDependencyResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    task_code: str | None = None
    task_title: str | None = None
    depends_on_task_code: str | None = None
    depends_on_task_title: str | None = None
    dependency_type: str
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CapacityWeek(BaseModel):
    week_start_date: date
    available_hours: float
    scheduled_hours: float = 0
    utilization_pct: float = 0


class EmployeeCapacityResponse(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    weeks: list[CapacityWeek]


class GanttTask(BaseModel):
    id: uuid.UUID
    task_code: str
    title: str
    scheduled_start_date: date | None
    scheduled_end_date: date | None
    planned_start_date: date | None
    planned_end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    progress: float
    estimated_hours: float
    actual_hours: float
    status: str
    priority: str
    assignees: list[dict] = []
    project_id: uuid.UUID


class GanttDependency(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    dependency_type: str


class GanttResponse(BaseModel):
    tasks: list[GanttTask]
    dependencies: list[GanttDependency]
