import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user)):
    from app.services.department_service import DepartmentService
    from uuid import UUID
    try:
        uid = UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return DepartmentService(db, current_user_id=uid)


@router.get("", response_model=APIResponse)
def list_departments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service=Depends(_get_service),
):
    departments, total = service.get_all(skip=skip, limit=limit)
    return APIResponse(
        success=True,
        message="Departments retrieved successfully",
        data={"departments": [d.model_dump() for d in departments], "total": total, "skip": skip, "limit": limit},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("HR", "create"))])
def create_department(department_in: DepartmentCreate, service=Depends(_get_service)):
    try:
        department = service.create(department_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Department created successfully",
        data={"department": department.model_dump()},
    )


@router.get("/{id}", response_model=APIResponse)
def get_department(id: uuid.UUID, service=Depends(_get_service)):
    try:
        department = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    return APIResponse(
        success=True,
        message="Department retrieved successfully",
        data={"department": department.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "edit"))])
def update_department(id: uuid.UUID, department_in: DepartmentUpdate, service=Depends(_get_service)):
    try:
        department = service.update(id, department_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Department updated successfully",
        data={"department": department.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("HR", "delete"))])
def delete_department(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Department deleted successfully")
