import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.core.rbac import UserContext, require_data_access
from app.schemas.common import APIResponse
from app.schemas.parent_project import ParentProjectCreate, ParentProjectUpdate, ParentProjectResponse
from app.schemas.project import ProjectResponse
from app.models.parent_project import ParentProject
from app.models.project import Project
from app.models.client import Client
from app.models.employee import Employee
from app.models.department import Department
from app.services.parent_project_metrics_service import ParentProjectMetricsService
from app.services.project_service import ProjectService
from app.services.audit_service import AuditService

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(db: Session, p: ParentProject, include_parts: bool = False) -> ParentProjectResponse:
    # Resolve names
    client_name = p.client.name if p.client else None
    pm_name = f"{p.project_manager.first_name} {p.project_manager.last_name}" if p.project_manager else None
    dept_name = p.department.name if p.department else None
    dept_code = p.department.code if p.department else None

    # Rolled-up part count
    part_count = db.scalar(
        select(func.count(Project.id)).where(
            and_(
                Project.parent_project_id == p.id,
                Project.is_active == True  # noqa: E712
            )
        )
    ) or 0

    parts_responses = []
    if include_parts:
        # Load active parts
        parts = db.scalars(
            select(Project)
            .where(
                and_(
                    Project.parent_project_id == p.id,
                    Project.is_active == True  # noqa: E712
                )
            )
            .options(
                selectinload(Project.client),
                selectinload(Project.project_manager),
                selectinload(Project.department)
            )
        ).all()

        project_service = ProjectService(db)
        for part in parts:
            tc, cc = project_service._get_task_counts(part.id)
            parts_responses.append(project_service._to_response(part, task_count=tc, completed_task_count=cc))

    return ParentProjectResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        client_id=p.client_id,
        client_name=client_name,
        project_manager_id=p.project_manager_id,
        project_manager_name=pm_name,
        department_id=p.department_id,
        department_name=dept_name,
        department_code=dept_code,
        is_active=p.is_active,
        created_at=p.created_at,
        updated_at=p.updated_at,
        part_count=part_count,
        status=p.status,
        progress=float(p.progress or 0.0),
        planned_start_date=p.planned_start_date,
        planned_end_date=p.planned_end_date,
        actual_start_date=p.actual_start_date,
        actual_end_date=p.actual_end_date,
        estimated_hours=float(p.estimated_hours or 0.0),
        actual_hours=float(p.actual_hours or 0.0),
        parts=parts_responses
    )


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def list_parent_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(ParentProject).where(ParentProject.is_active == True)  # noqa: E712

    if client_id:
        stmt = stmt.where(ParentProject.client_id == client_id)
    if search:
        stmt = stmt.where(ParentProject.name.ilike(f"%{search}%"))
    if status:
        stmt = stmt.where(ParentProject.status == status)

    stmt = stmt.options(
        selectinload(ParentProject.client),
        selectinload(ParentProject.project_manager),
        selectinload(ParentProject.department)
    ).order_by(ParentProject.created_at.desc()).offset(skip).limit(limit)

    results = db.scalars(stmt).all()

    total_stmt = select(func.count(ParentProject.id)).where(ParentProject.is_active == True)  # noqa: E712
    if client_id:
        total_stmt = total_stmt.where(ParentProject.client_id == client_id)
    if search:
        total_stmt = total_stmt.where(ParentProject.name.ilike(f"%{search}%"))
    if status:
        total_stmt = total_stmt.where(ParentProject.status == status)
    total = db.scalar(total_stmt) or 0

    responses = [_to_response(db, p, include_parts=False) for p in results]

    return APIResponse(
        success=True,
        message="Projects retrieved successfully",
        data={
            "projects": [r.model_dump() for r in responses],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Projects", "create"))],
)
def create_parent_project(
    body: ParentProjectCreate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    current_uid = uuid.UUID(current_user_id)

    # 1. Validate Parent Project identity
    existing = db.scalar(select(ParentProject).where(ParentProject.name == body.name, ParentProject.is_active == True))  # noqa: E712
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project with the name '{body.name}' already exists."
        )

    # Validate Client
    client = db.get(Client, body.client_id)
    if not client or not client.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected client not found or inactive.")

    # Validate Department if provided
    if body.department_id:
        dept = db.get(Department, body.department_id)
        if not dept or not dept.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected department not found or inactive.")

    # Validate Project Manager
    if body.project_manager_id:
        pm = db.get(Employee, body.project_manager_id)
        if not pm or not pm.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected project manager not found or inactive.")

    try:
        # Create ParentProject
        parent = ParentProject(
            name=body.name.strip(),
            description=body.description.strip() if body.description else None,
            client_id=body.client_id,
            project_manager_id=body.project_manager_id,
            department_id=body.department_id,
            created_by=current_uid,
        )
        db.add(parent)
        db.flush()

        # Create Parts (using ProjectService)
        project_service = ProjectService(db, current_user_id=current_uid)
        for part_in in body.parts:
            # Overwrite part client/manager/dept with parent settings for consistency
            part_in.client_id = body.client_id
            part_in.project_manager_id = body.project_manager_id
            part_in.department_id = body.department_id
            part_in.name = body.name.strip() # Package name is parent project name

            part_resp = project_service.create(part_in)

            # Link part to parent project
            part_db = db.get(Project, part_resp.id)
            if part_db:
                part_db.parent_project_id = parent.id

        db.flush()

        # Initial metrics calculation
        ParentProjectMetricsService.recalculate(db, parent.id)
        db.commit()

        # Reload with joined relations
        db.refresh(parent)
        # Fetch detailed parent
        parent_details = db.scalar(
            select(ParentProject)
            .where(ParentProject.id == parent.id)
            .options(
                selectinload(ParentProject.client),
                selectinload(ParentProject.project_manager),
                selectinload(ParentProject.department)
            )
        )

        AuditService.log(
            db, "parent_project", parent.id, "CREATE",
            performed_by=current_uid,
            new_value={"name": parent.name, "client_id": str(parent.client_id)}
        )

        return APIResponse(
            success=True,
            message="Project created successfully",
            data={"project": _to_response(db, parent_details, include_parts=True).model_dump()}
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "view"))],
)
def get_parent_project(
    id: uuid.UUID,
    db: Session = Depends(get_db),
):
    parent = db.scalar(
        select(ParentProject)
        .where(and_(ParentProject.id == id, ParentProject.is_active == True))  # noqa: E712
        .options(
            selectinload(ParentProject.client),
            selectinload(ParentProject.project_manager),
            selectinload(ParentProject.department)
        )
    )
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    return APIResponse(
        success=True,
        message="Project retrieved successfully",
        data={"project": _to_response(db, parent, include_parts=True).model_dump()}
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "edit"))],
)
def update_parent_project(
    id: uuid.UUID,
    body: ParentProjectUpdate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    parent = db.get(ParentProject, id)
    if not parent or not parent.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    current_uid = uuid.UUID(current_user_id)
    update_data = body.model_dump(exclude_unset=True)

    # Name validation
    if "name" in update_data and update_data["name"] != parent.name:
        existing = db.scalar(select(ParentProject).where(ParentProject.name == update_data["name"], ParentProject.is_active == True))  # noqa: E712
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"A project with the name '{update_data['name']}' already exists.")

    old_values = {k: getattr(parent, k) for k in update_data if hasattr(parent, k)}

    try:
        # Update fields
        for k, v in update_data.items():
            setattr(parent, k, v)

        # Propagate client/manager/dept and name updates to all active parts
        parts = db.scalars(select(Project).where(Project.parent_project_id == id, Project.is_active == True)).all()  # noqa: E712
        for part in parts:
            if "client_id" in update_data:
                part.client_id = update_data["client_id"]
            if "project_manager_id" in update_data:
                part.project_manager_id = update_data["project_manager_id"]
            if "department_id" in update_data:
                part.department_id = update_data["department_id"]
            if "name" in update_data:
                part.name = update_data["name"]

        db.flush()

        # Recalculate rolled-up metrics
        ParentProjectMetricsService.recalculate(db, parent.id)
        db.commit()

        # Reload
        db.refresh(parent)
        parent_details = db.scalar(
            select(ParentProject)
            .where(ParentProject.id == parent.id)
            .options(
                selectinload(ParentProject.client),
                selectinload(ParentProject.project_manager),
                selectinload(ParentProject.department)
            )
        )

        AuditService.log(
            db, "parent_project", parent.id, "UPDATE",
            performed_by=current_uid,
            old_value=old_values,
            new_value=update_data
        )

        return APIResponse(
            success=True,
            message="Project updated successfully",
            data={"project": _to_response(db, parent_details, include_parts=True).model_dump()}
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Projects", "activate"))],
)
def delete_parent_project(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    parent = db.get(ParentProject, id)
    if not parent or not parent.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    current_uid = uuid.UUID(current_user_id)

    # Load active parts
    parts = db.scalars(select(Project).where(Project.parent_project_id == id, Project.is_active == True)).all()  # noqa: E712

    try:
        project_service = ProjectService(db, current_user_id=current_uid)
        # Attempt to delete all parts (this runs safety checks for active tasks under parts)
        for part in parts:
            project_service.delete(part.id)

        # Soft delete parent project
        parent.is_active = False
        db.commit()

        AuditService.log(
            db, "parent_project", parent.id, "DELETE",
            performed_by=current_uid,
            old_value={"name": parent.name, "is_active": True},
            new_value={"is_active": False}
        )

        return APIResponse(
            success=True,
            message="Project deleted successfully"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/holidays/list", response_model=APIResponse)
def list_holidays(db: Session = Depends(get_db)):
    """
    List all holiday dates in ascending order.
    """
    from app.models.holiday import Holiday
    holidays = db.scalars(select(Holiday.date).order_by(Holiday.date)).all()
    return APIResponse(
        success=True,
        message="Holidays retrieved successfully",
        data={"holidays": [h.isoformat() for h in holidays]},
    )
