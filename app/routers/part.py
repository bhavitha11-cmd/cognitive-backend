import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload

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
from app.models.project import Project

router = APIRouter(
    prefix="/parts",
    tags=["Parts"],
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


# ── Legacy/Existing endpoint ──────────────────────────────────────────────────

@router.get("/{part_number}/project-details", response_model=APIResponse)
def get_part_project_details(part_number: str, db: Session = Depends(get_db)):
    """
    Fetches details of the project associated with the given Part Number (project_code).
    """
    project = db.scalar(
        select(Project)
        .where(Project.project_code == part_number, Project.is_active == True)  # noqa: E712
        .options(
            selectinload(Project.client),
            selectinload(Project.project_manager)
        )
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No project is associated with the selected Part Number.",
        )

    client_name = project.client.name if project.client else None
    pm_name = None
    if project.project_manager:
        pm = project.project_manager
        pm_name = f"{pm.first_name} {pm.last_name}"

    data = {
        "partNumber": project.project_code,
        "partName": project.part_name,
        "projectId": str(project.id),
        "projectName": project.name,
        "packageName": project.name,
        "clientName": client_name,
        "projectManager": pm_name,
        "departmentId": str(project.department_id) if project.department_id else None,
        "status": project.status,
        "priority": project.priority,
        "plannedEndDate": project.planned_end_date.isoformat() if project.planned_end_date else None,
        "plannedStartDate": project.planned_start_date.isoformat() if project.planned_start_date else None,
    }

    return APIResponse(
        success=True,
        message="Project details retrieved successfully",
        data=data,
    )


# ── Part CRUD Endpoints (mapped from old Project CRUD) ─────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "view"))],
)
def list_parts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    parent_project_id: Optional[uuid.UUID] = Query(None),
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status filter. Must be one of: {sorted(VALID_STATUSES)}",
        )
    
    # We can fetch parts using ProjectService. To support parent_project_id filter, we'll custom query if needed,
    # or let the repo handle it. But to be clean and simple, we can filter using service or customize here.
    # Let's inspect get_all or count or repo methods:
    # Actually, we can fetch projects (parts) using service.get_all, and if parent_project_id is specified, filter it.
    projects, total = service.get_all(
        skip=skip, limit=limit, search=search, client_id=client_id, status=status,
        user_context=user_ctx,
    )
    
    # Filter by parent_project_id if requested (since it's a new filter)
    if parent_project_id:
        filtered = []
        for p in projects:
            part_db = service.repo.get_by_id(p.id)
            if part_db and part_db.parent_project_id == parent_project_id:
                filtered.append(p)
        projects = filtered
        total = len(projects)

    return APIResponse(
        success=True,
        message="Parts retrieved successfully",
        data={
            "projects": [p.model_dump() for p in projects],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "view"))],
)
def get_part(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        project = service.get_by_id(id, user_context=user_ctx)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")
    
    # Include parent project info if available
    part_db = service.repo.get_by_id(id)
    resp_data = project.model_dump()
    resp_data["parent_project_id"] = str(part_db.parent_project_id) if part_db and part_db.parent_project_id else None
    
    return APIResponse(
        success=True,
        message="Part retrieved successfully",
        data={"project": resp_data},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "edit"))],
)
def update_part(
    id: uuid.UUID,
    project_in: ProjectUpdate,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    from app.core.rbac import DataAccessLevel
    try:
        project_obj = service.repo.get_by_id(id)
        if not project_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")

        is_admin = user_ctx.is_super_admin or user_ctx.data_access_level == DataAccessLevel.FULL
        is_pm = (project_obj.project_manager_id == user_ctx.employee_id)
        is_creator = (project_obj.created_by == user_ctx.employee_id)

        if not is_admin and not is_pm and not is_creator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the project manager, creator, or an administrator can edit this part"
            )

        project = service.update(id, project_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Part updated successfully",
        data={"project": project.model_dump()},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "activate"))],
)
def delete_part(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    from app.core.rbac import DataAccessLevel
    try:
        project_obj = service.repo.get_by_id(id)
        if not project_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")

        is_admin = user_ctx.is_super_admin or user_ctx.data_access_level == DataAccessLevel.FULL
        is_pm = (project_obj.project_manager_id == user_ctx.employee_id)
        is_creator = (project_obj.created_by == user_ctx.employee_id)

        if not is_admin and not is_pm and not is_creator:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the project manager, creator, or an administrator can delete this part"
            )

        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Part deleted successfully")


@router.get(
    "/{id}/stats",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "view"))],
)
def get_part_stats(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        service.get_by_id(id, user_context=user_ctx)
        stats = service.get_project_stats(id)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Part statistics retrieved successfully",
        data={"stats": stats},
    )


class StatusPatchBody(BaseModel):
    status: str
    reason: Optional[str] = None


@router.patch(
    "/{id}/status",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "edit"))],
)
def update_part_status(
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

    try:
        current = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Part not found")

    allowed = STATUS_TRANSITIONS.get(current.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition part from '{current.status}' to '{new_status}'. "
                f"Allowed transitions: {sorted(allowed) if allowed else 'none'}"
            ),
        )

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
        message=f"Part status updated to '{new_status}'",
        data={"project": updated.model_dump()},
    )


# ── Part Member Management ────────────────────────────────────────────────────

@router.get(
    "/{id}/members",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "view"))],
)
def list_part_members(
    id: uuid.UUID,
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    try:
        service.get_by_id(id, user_context=user_ctx)
        members = service.get_members(id)
    except ValueError as e:
        if "permission" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Part members retrieved successfully",
        data={"members": [m.model_dump() for m in members], "total": len(members)},
    )


@router.post(
    "/{id}/members",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Parts", "edit"))],
)
def add_part_member(
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
        message="Member added to part",
        data={"member": member.model_dump()},
    )


@router.delete(
    "/{id}/members/{member_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Parts", "edit"))],
)
def remove_part_member(
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
    return APIResponse(success=True, message="Member removed from part")


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Parts", "create"))],
)
def create_part(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    current_uid = uuid.UUID(current_user_id)
    
    # 1. Check if part number already exists
    from app.models.project import Project
    from app.models.parent_project import ParentProject
    
    existing = db.scalar(select(Project).where(Project.project_code == body.part_number, Project.is_active == True))  # noqa: E712
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A part with part number '{body.part_number}' already exists."
        )

    # 2. Check parent project association
    if not body.parent_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parent project association is required."
        )
        
    parent = db.get(ParentProject, body.parent_project_id)
    if not parent or not parent.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent project not found or inactive."
        )

    # 3. Create the Part (Project)
    db_project = Project(
        parent_project_id=body.parent_project_id,
        project_code=body.part_number,
        name=body.name,
        part_name=body.part_name,
        description=body.description,
        client_id=body.client_id,
        project_manager_id=body.project_manager_id,
        department_id=body.department_id,
        status=body.status,
        priority=body.priority,
        is_billable=body.is_billable,
        planned_start_date=body.planned_start_date,
        planned_end_date=body.planned_end_date,
        estimated_hours=body.estimated_hours,
        contract_hours=body.contract_hours,
        invoice_status=body.invoice_status,
        tok_form=body.tok_form,
        feedback_status=body.feedback_status,
        status_reason=body.status_reason,
        is_active=True,
    )
    
    try:
        db.add(db_project)
        db.commit()
        db.refresh(db_project)

        # 4. Trigger Parent Project roll-up metrics recalculation
        from app.services.parent_project_metrics_service import ParentProjectMetricsService
        ParentProjectMetricsService.recalculate(db, parent.id)
        
        # 5. Log audit
        from app.services.audit_service import AuditService
        AuditService.log(
            db, "project", db_project.id, "CREATE",
            performed_by=current_uid,
            new_value=body.model_dump(mode="json")
        )
        
        # Format response
        from app.services.project_service import ProjectService
        project_service = ProjectService(db, current_user_id=current_uid)
        response_data = project_service._to_response(db_project)
        
        return APIResponse(
            success=True,
            message="Part created successfully",
            data={"part": response_data.model_dump()}
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

