import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.department import DepartmentCreate, DepartmentUpdate

from app.dependencies import get_current_user

router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=APIResponse)
def list_departments(db: Session = Depends(get_db)):
    from app.services.department_service import DepartmentService

    service = DepartmentService(db)
    departments = service.get_all()
    return APIResponse(
        success=True,
        message="Departments retrieved successfully",
        data={"departments": [d.model_dump() for d in departments]},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_department(department_in: DepartmentCreate, db: Session = Depends(get_db)):
    from app.services.department_service import DepartmentService

    service = DepartmentService(db)
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
def get_department(id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services.department_service import DepartmentService

    service = DepartmentService(db)
    try:
        department = service.get_by_id(id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )
    return APIResponse(
        success=True,
        message="Department retrieved successfully",
        data={"department": department.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse)
def update_department(
    id: uuid.UUID, department_in: DepartmentUpdate, db: Session = Depends(get_db)
):
    from app.services.department_service import DepartmentService

    service = DepartmentService(db)
    try:
        department = service.update(id, department_in)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return APIResponse(
        success=True,
        message="Department updated successfully",
        data={"department": department.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse)
def delete_department(id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services.department_service import DepartmentService

    service = DepartmentService(db)
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Department deleted successfully",
        data=None,
    )
