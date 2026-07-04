import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.core.rbac import UserContext, require_data_access
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return TaskService(db, current_user_id=uid)


# ── Task CRUD ──────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    project_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    dept_cat: str | None = Query(default=None),
    search: str | None = Query(default=None),
    service: TaskService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    tasks, total = service.get_all(
        skip=skip,
        limit=limit,
        project_id=project_id,
        status=status,
        dept_cat=dept_cat,
        search=search,
        user_context=user_ctx,
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
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        task = service.create(data, user_context=user_ctx)
    except ValueError as e:
        msg = str(e).lower()
        if "not a member" in msg or "permission" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        code = status.HTTP_404_NOT_FOUND if "not found" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Task created successfully",
        data={"task": task.model_dump()},
    )


@router.get(
    "/next-code/{project_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def get_next_task_code(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Returns the next available task code for a project.
    Scans ALL existing task codes (bypasses RBAC) to find the highest suffix.
    """
    from app.models.project import Project
    from app.models.task import Task
    from sqlalchemy import select, func

    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    part_number = project.project_code

    # Find all task codes for this project to determine the highest suffix
    task_codes = list(db.scalars(
        select(Task.task_code).where(Task.project_id == project_id)
    ).all())

    max_suffix = 0
    for code in task_codes:
        if code and '-' in code:
            suffix_str = code.rsplit('-', 1)[-1]
            try:
                suffix_num = int(suffix_str)
                if suffix_num > max_suffix:
                    max_suffix = suffix_num
            except ValueError:
                pass

    next_suffix = str(max_suffix + 1).zfill(3)
    next_code = f"{part_number}-{next_suffix}"

    return APIResponse(
        success=True,
        message="Next task code generated",
        data={
            "next_code": next_code,
            "part_number": part_number,
            "suffix": next_suffix,
            "existing_count": len(task_codes),
        },
    )


@router.get(
    "/by-project/{project_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def get_tasks_by_project(
    project_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    service: TaskService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db),
):
    from app.repositories.project_repository import ProjectRepository
    proj_repo = ProjectRepository(db)
    if not proj_repo.is_visible_to_user(project_id, user_ctx):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view tasks for this project",
        )
    all_tasks = service.get_by_project(project_id)
    total = len(all_tasks)
    tasks = all_tasks[skip: skip + limit]
    return APIResponse(
        success=True,
        message="Tasks retrieved successfully",
        data={"tasks": [t.model_dump() for t in tasks], "total": total, "skip": skip, "limit": limit},
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def get_task(
    id: uuid.UUID,
    service: TaskService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        task = service.get_by_id(id, user_context=user_ctx)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
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
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db),
):
    from app.core.rbac import DataAccessLevel
    from app.models.task import Task as TaskModel

    # Load existing task to check ownership
    existing_task = db.get(TaskModel, id)
    if not existing_task or not existing_task.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    is_creator = (existing_task.created_by == user_ctx.employee_id)
    is_admin = user_ctx.is_super_admin or user_ctx.data_access_level == DataAccessLevel.FULL

    # If user is NOT the creator and NOT admin → restrict to status/progress only
    if not is_creator and not is_admin:
        restricted = TaskUpdate(
            status=data.status,
            progress=data.progress,
        )
        data = restricted

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
    dependencies=[Depends(require_permission("Tasks", "activate"))],
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
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db),
):
    from app.core.rbac import DataAccessLevel
    from app.models.task_assignment import TaskAssignment
    from sqlalchemy import select

    # SELF-level users may only update status on tasks assigned to them
    if user_ctx.data_access_level == DataAccessLevel.SELF:
        assigned = db.scalars(
            select(TaskAssignment).where(
                TaskAssignment.task_id == id,
                TaskAssignment.employee_id == user_ctx.employee_id,
                TaskAssignment.status != "CANCELLED",
            )
        ).first()
        if not assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update status of tasks assigned to you",
            )

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
