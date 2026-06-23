import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.core.rbac import UserContext, require_data_access
from app.schemas.common import APIResponse
from app.schemas.project import (
    VALID_STATUSES,
    ProjectCreate,
    ProjectUpdate,
    ProjectMemberAdd,
)

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(get_current_user)],
)

# ── Valid status transitions ──────────────────────────────────────────────────
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "Yet To Start": {"In Progress", "On Hold", "Completed", "Cancelled"},
    "In Progress":  {"Yet To Start", "On Hold", "Completed", "Cancelled"},
    "On Hold":      {"Yet To Start", "In Progress", "Completed", "Cancelled"},
    "Completed":    {"Yet To Start", "In Progress", "On Hold", "Cancelled"},
    "Cancelled":    {"Yet To Start", "In Progress", "On Hold", "Completed"},
}


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.project_service import ProjectService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return ProjectService(db, current_user_id=uid)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status filter. Must be one of: {sorted(VALID_STATUSES)}",
        )
    projects, total = service.get_all(
        skip=skip, limit=limit, search=search, client_id=client_id, status=status,
        user_context=user_ctx,
    )
    return APIResponse(
        success=True,
        message="Projects retrieved successfully",
        data={
            "projects": [p.model_dump() for p in projects],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Projects", "create"))],
)
def create_project(project_in: ProjectCreate, service=Depends(_get_service)):
    try:
        project = service.create(project_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Project created successfully",
        data={"project": project.model_dump()},
    )


@router.post(
    "/admin/recalculate-all",
    response_model=APIResponse,
)
def recalculate_all_projects(
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    from app.core.rbac import DataAccessLevel
    if not user_ctx.is_super_admin and user_ctx.data_access_level != DataAccessLevel.FULL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger a full project metrics recalculation",
        )
    result = service.recalculate_all()
    return APIResponse(
        success=True,
        message=f"Recalculated metrics for {result['updated']}/{result['total']} projects",
        data=result,
    )


@router.get("/holidays/list", response_model=APIResponse)
def list_holidays(db: Session = Depends(get_db)):
    from app.models.holiday import Holiday
    from sqlalchemy import select
    holidays = db.scalars(select(Holiday.date).order_by(Holiday.date)).all()
    return APIResponse(
        success=True,
        message="Holidays retrieved successfully",
        data={"holidays": [h.isoformat() for h in holidays]},
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def get_project(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        project = service.get_by_id(id, user_context=user_ctx)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return APIResponse(
        success=True,
        message="Project retrieved successfully",
        data={"project": project.model_dump()},
    )


@router.get(
    "/{id}/stats",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def get_project_stats(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        # Verify user can see this project before returning stats
        service.get_by_id(id, user_context=user_ctx)
        stats = service.get_project_stats(id)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Project statistics retrieved successfully",
        data={"stats": stats},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def update_project(id: uuid.UUID, project_in: ProjectUpdate, service=Depends(_get_service)):
    try:
        project = service.update(id, project_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Project updated successfully",
        data={"project": project.model_dump()},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "delete"))],
)
def delete_project(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Project deleted successfully")


class StatusPatchBody(BaseModel):
    status: str
    reason: Optional[str] = None


@router.patch(
    "/{id}/status",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def update_project_status(
    id: uuid.UUID,
    body: StatusPatchBody,
    service=Depends(_get_service),
):
    new_status = body.status
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{new_status}'. Must be one of: {sorted(VALID_STATUSES)}",
        )

    # Fetch current status to validate transition
    try:
        current = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    allowed = STATUS_TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition project from '{current.status}' to '{new_status}'. "
                f"Allowed transitions: {sorted(allowed) if allowed else 'none'}"
            ),
        )

    # Enforce reason requirement for Cancelled transitions
    if new_status == "Cancelled" or current.status == "Cancelled":
        if not body.reason or not body.reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reason is required for this status change."
            )

    try:
        updated = service.update_status(id, new_status, body.reason)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))

    return APIResponse(
        success=True,
        message=f"Project status updated to '{new_status}'",
        data={"project": updated.model_dump()},
    )


# ── Project Member Management ─────────────────────────────────────────────────

@router.get(
    "/{id}/members",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def list_project_members(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        # Verify the caller can see this project first
        service.get_by_id(id, user_context=user_ctx)
        members = service.get_members(id)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Project members retrieved successfully",
        data={"members": [m.model_dump() for m in members], "total": len(members)},
    )


@router.post(
    "/{id}/members",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def add_project_member(
    id: uuid.UUID,
    body: ProjectMemberAdd,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        member = service.add_member(
            project_id=id,
            employee_id=body.employee_id,
            role=body.role,
            allocation_pct=body.allocation_pct,
            user_context=user_ctx,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Member added to project",
        data={"member": member.model_dump()},
    )


@router.delete(
    "/{id}/members/{member_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def remove_project_member(
    id: uuid.UUID,
    member_id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        service.remove_member(project_id=id, member_id=member_id, user_context=user_ctx)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Member removed from project")
