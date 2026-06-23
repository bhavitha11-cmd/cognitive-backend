import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.dependencies import get_current_user
from app.models.project import Project
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/parts",
    tags=["Parts"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{part_number}/project-details", response_model=APIResponse)
def get_part_project_details(part_number: str, db: Session = Depends(get_db)):
    """
    Fetches details of the project associated with the given Part Number (project_code).
    """
    project = db.scalar(
        select(Project)
        .where(Project.project_code == part_number, Project.is_active == True)
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
