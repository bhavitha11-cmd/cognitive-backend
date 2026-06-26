import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.task_template import (
    TaskTemplateCreate,
    TaskTemplateResponse,
    TaskTemplateSearchItem,
    TaskTemplateUpdate,
)

router = APIRouter(
    prefix="/task-templates",
    tags=["Task Templates"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user)):
    from app.services.task_template_service import TaskTemplateService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return TaskTemplateService(db, current_user_id=uid)


class BulkStatusRequest(BaseModel):
    ids: list[uuid.UUID]
    is_active: bool


@router.get("", response_model=APIResponse)
def list_task_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    service=Depends(_get_service),
):
    templates, total = service.get_all(
        skip=skip, limit=limit, search=search,
        is_active=is_active, sort_by=sort_by, sort_order=sort_order,
    )
    return APIResponse(
        success=True,
        message="Task templates retrieved successfully",
        data={
            "templates": [t.model_dump() for t in templates],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get("/search", response_model=APIResponse)
def search_task_templates(
    q: str | None = Query(None),
    service=Depends(_get_service),
):
    items = service.search(q=q)
    return APIResponse(
        success=True,
        message="Search results",
        data={"templates": [i.model_dump() for i in items]},
    )


@router.get("/{id}", response_model=APIResponse)
def get_task_template(id: uuid.UUID, service=Depends(_get_service)):
    try:
        template = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task template not found")
    return APIResponse(
        success=True,
        message="Task template retrieved successfully",
        data={"template": template.model_dump()},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("TaskTemplate", "create"))])
def create_task_template(
    data_in: TaskTemplateCreate,
    service=Depends(_get_service),
):
    try:
        template = service.create(data_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Task template created successfully",
        data={"template": template.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("TaskTemplate", "edit"))])
def update_task_template(
    id: uuid.UUID,
    data_in: TaskTemplateUpdate,
    service=Depends(_get_service),
):
    try:
        template = service.update(id, data_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Task template updated successfully",
        data={"template": template.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("TaskTemplate", "delete"))])
def delete_task_template(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(success=True, message="Task template deleted successfully")


@router.patch("/bulk-status", response_model=APIResponse,
              dependencies=[Depends(require_permission("TaskTemplate", "edit"))])
def bulk_status_task_templates(req: BulkStatusRequest, service=Depends(_get_service)):
    count = service.bulk_status(req.ids, req.is_active)
    return APIResponse(
        success=True,
        message=f"{count} template(s) {'activated' if req.is_active else 'deactivated'} successfully",
    )
