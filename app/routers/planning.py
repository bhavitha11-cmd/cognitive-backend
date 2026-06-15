from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.planning import (
    EmployeeScheduleCreate, EmployeeScheduleUpdate, TaskDependencyCreate,
)
from app.services.planning_service import PlanningService

router = APIRouter(
    prefix="/planning",
    tags=["Planning"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> PlanningService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        uid = None
    return PlanningService(db, current_user_id=uid)


# ── Employee Schedules ─────────────────────────────────────────────────────────

@router.post("/schedules", response_model=APIResponse, status_code=201)
def create_schedule(
    data: EmployeeScheduleCreate,
    service: PlanningService = Depends(_get_service),
):
    result = service.create_schedule(data)
    return APIResponse(success=True, message="Schedule created", data={"schedule": result.model_dump()})


@router.put("/schedules/{schedule_id}", response_model=APIResponse)
def update_schedule(
    schedule_id: uuid.UUID,
    data: EmployeeScheduleUpdate,
    service: PlanningService = Depends(_get_service),
):
    result = service.update_schedule(schedule_id, data)
    return APIResponse(success=True, message="Schedule updated", data={"schedule": result.model_dump()})


@router.get("/schedules", response_model=APIResponse)
def list_schedules(
    employee_id: uuid.UUID = Query(...),
    from_date: date = Query(...),
    to_date: date = Query(...),
    service: PlanningService = Depends(_get_service),
):
    schedules = service.get_employee_schedules(employee_id, from_date, to_date)
    return APIResponse(success=True, message="Schedules retrieved", data={"schedules": [s.model_dump() for s in schedules]})


# ── Employee Capacity ──────────────────────────────────────────────────────────

@router.get("/capacity/{employee_id}", response_model=APIResponse)
def get_capacity(
    employee_id: uuid.UUID,
    from_date: date = Query(...),
    to_date: date = Query(...),
    service: PlanningService = Depends(_get_service),
):
    result = service.get_employee_capacity(employee_id, from_date, to_date)
    return APIResponse(success=True, message="Capacity retrieved", data=result.model_dump())


# ── Task Dependencies ──────────────────────────────────────────────────────────

@router.post("/dependencies", response_model=APIResponse, status_code=201)
def create_dependency(
    data: TaskDependencyCreate,
    service: PlanningService = Depends(_get_service),
):
    result = service.create_dependency(data)
    return APIResponse(success=True, message="Dependency created", data={"dependency": result.model_dump()})


@router.delete("/dependencies/{dependency_id}", response_model=APIResponse)
def delete_dependency(
    dependency_id: uuid.UUID,
    service: PlanningService = Depends(_get_service),
):
    service.delete_dependency(dependency_id)
    return APIResponse(success=True, message="Dependency deleted")


@router.get("/dependencies/{task_id}", response_model=APIResponse)
def get_task_dependencies(
    task_id: uuid.UUID,
    service: PlanningService = Depends(_get_service),
):
    deps = service.get_task_dependencies(task_id)
    return APIResponse(success=True, message="Dependencies retrieved", data={"dependencies": [d.model_dump() for d in deps]})


@router.get("/project-dependencies/{project_id}", response_model=APIResponse)
def get_project_dependencies(
    project_id: uuid.UUID,
    service: PlanningService = Depends(_get_service),
):
    deps = service.get_project_dependencies(project_id)
    return APIResponse(success=True, message="Project dependencies retrieved", data={"dependencies": [d.model_dump() for d in deps]})


# ── Gantt ──────────────────────────────────────────────────────────────────────

@router.get("/gantt/{project_id}", response_model=APIResponse)
def get_gantt(
    project_id: uuid.UUID,
    service: PlanningService = Depends(_get_service),
):
    result = service.get_gantt_data(project_id)
    return APIResponse(success=True, message="Gantt data retrieved", data=result.model_dump())


@router.post("/schedule/{project_id}", response_model=APIResponse)
def schedule_project(
    project_id: uuid.UUID,
    service: PlanningService = Depends(_get_service),
):
    result = service.schedule_project(project_id)
    return APIResponse(success=True, message="Project scheduled successfully", data=result.model_dump())
