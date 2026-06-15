import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.scope_of_work import ScopeCreate, ScopeUpdate

router = APIRouter(
    prefix="/scope-of-work",
    tags=["Scope of Work"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from uuid import UUID as _UUID

    from app.services.scope_of_work_service import ScopeService

    try:
        uid = _UUID(current_user_id)
    except (ValueError, AttributeError):
        uid = None
    return ScopeService(db, current_user_id=uid)


@router.get("", response_model=APIResponse)
def list_scopes(
    department_category: str | None = Query(None, description="Filter by department category"),
    include_inactive: bool = Query(False, description="Include inactive records"),
    service=Depends(_get_service),
):
    scopes = service.get_all(
        department_category=department_category,
        include_inactive=include_inactive,
    )
    return APIResponse(
        success=True,
        message="Scopes of work retrieved successfully",
        data={"scopes": [s.model_dump() for s in scopes], "total": len(scopes)},
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Settings", "create"))],
)
def create_scope(scope_in: ScopeCreate, service=Depends(_get_service)):
    try:
        scope = service.create(scope_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Scope of work created successfully",
        data={"scope": scope.model_dump()},
    )


@router.get("/{id}", response_model=APIResponse)
def get_scope(id: uuid.UUID, service=Depends(_get_service)):
    try:
        scope = service.get_by_id(id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scope of work not found"
        )
    return APIResponse(
        success=True,
        message="Scope of work retrieved successfully",
        data={"scope": scope.model_dump()},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def update_scope(id: uuid.UUID, scope_in: ScopeUpdate, service=Depends(_get_service)):
    try:
        scope = service.update(id, scope_in)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Scope of work updated successfully",
        data={"scope": scope.model_dump()},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "delete"))],
)
def delete_scope(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Scope of work deleted successfully")
