import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.task import (
    TaskAssignmentCreate,
    TaskAssignmentUpdate,
    TaskCreate,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> TaskService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        uid = None
    return TaskService(db, current_user_id=uid)


# ── Task CRUD ──────────────────────────────────────────────────────────────────

@router.get("", response_model=APIResponse)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    project_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    dept_cat: str | None = Query(default=None),
    search: str | None = Query(default=None),
    service: TaskService = Depends(_get_service),
):
    tasks, total = service.get_all(
        skip=skip,
        limit=limit,
        project_id=project_id,
        status=status,
        dept_cat=dept_cat,
        search=search,
    )
    return APIResponse(
        success=True,
        message="Tasks retrieved successfully",
        data={
            "tasks": [t.model_dump() for t in tasks],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Tasks", "create"))],
)
def create_task(
    data: TaskCreate,
    service: TaskService = Depends(_get_service),
):
    try:
        task = service.create(data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Task created successfully",
        data={"task": task.model_dump()},
    )


@router.get("/by-project/{project_id}", response_model=APIResponse)
def get_tasks_by_project(
    project_id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    tasks = service.get_by_project(project_id)
    return APIResponse(
        success=True,
        message="Tasks retrieved successfully",
        data={"tasks": [t.model_dump() for t in tasks], "total": len(tasks)},
    )


@router.get("/{id}", response_model=APIResponse)
def get_task(
    id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    try:
        task = service.get_by_id(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Task retrieved successfully",
        data={"task": task.model_dump()},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def update_task(
    id: uuid.UUID,
    data: TaskUpdate,
    service: TaskService = Depends(_get_service),
):
    try:
        task = service.update(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Task updated successfully",
        data={"task": task.model_dump()},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "delete"))],
)
def delete_task(
    id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    try:
        service.delete(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Task deleted successfully")


@router.patch(
    "/{id}/status",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def update_task_status(
    id: uuid.UUID,
    data: TaskStatusUpdate,
    service: TaskService = Depends(_get_service),
):
    update_payload = TaskUpdate(status=data.status)
    if data.progress is not None:
        update_payload = TaskUpdate(status=data.status, progress=data.progress)
    try:
        task = service.update(id, update_payload)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Task status updated successfully",
        data={"task": task.model_dump()},
    )


# ── Assignments ────────────────────────────────────────────────────────────────

@router.post(
    "/{id}/assignments",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def assign_employee(
    id: uuid.UUID,
    data: TaskAssignmentCreate,
    service: TaskService = Depends(_get_service),
):
    try:
        assignment = service.assign_employee(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Employee assigned to task",
        data={"assignment": assignment.model_dump()},
    )


@router.put(
    "/{id}/assignments/{assignment_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def update_assignment(
    id: uuid.UUID,
    assignment_id: uuid.UUID,
    data: TaskAssignmentUpdate,
    service: TaskService = Depends(_get_service),
):
    try:
        assignment = service.update_assignment(id, assignment_id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Assignment updated successfully",
        data={"assignment": assignment.model_dump()},
    )


@router.delete(
    "/{id}/assignments/{assignment_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def remove_assignment(
    id: uuid.UUID,
    assignment_id: uuid.UUID,
    service: TaskService = Depends(_get_service),
):
    try:
        service.remove_assignment(id, assignment_id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Assignment removed successfully")
