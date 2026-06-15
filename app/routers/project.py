import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.project import (
    VALID_STATUSES,
    ProjectCreate,
    ProjectUpdate,
)

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(get_current_user)],
)

# ── Valid status transitions ──────────────────────────────────────────────────
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":     {"ACTIVE", "CANCELLED"},
    "ACTIVE":    {"ON_HOLD", "COMPLETED", "CANCELLED"},
    "ON_HOLD":   {"ACTIVE", "CANCELLED"},
    "COMPLETED": {"ACTIVE"},          # allow re-open
    "CANCELLED": {"DRAFT"},           # allow revive
}


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.project_service import ProjectService
    try:
        uid = uuid.UUID(current_user_id)
    except ValueError:
        uid = None
    return ProjectService(db, current_user_id=uid)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=APIResponse)
def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    service=Depends(_get_service),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status filter. Must be one of: {sorted(VALID_STATUSES)}",
        )
    projects, total = service.get_all(
        skip=skip, limit=limit, search=search, client_id=client_id, status=status
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


@router.get("/{id}", response_model=APIResponse)
def get_project(id: uuid.UUID, service=Depends(_get_service)):
    try:
        project = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return APIResponse(
        success=True,
        message="Project retrieved successfully",
        data={"project": project.model_dump()},
    )


@router.get("/{id}/stats", response_model=APIResponse)
def get_project_stats(id: uuid.UUID, service=Depends(_get_service)):
    try:
        stats = service.get_project_stats(id)
    except ValueError as e:
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

    try:
        updated = service.update(id, ProjectUpdate(status=new_status))
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))

    return APIResponse(
        success=True,
        message=f"Project status updated to '{new_status}'",
        data={"project": updated.model_dump()},
    )
