import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.designation import DesignationCreate, DesignationUpdate

from app.dependencies import get_current_user

router = APIRouter(
    prefix="/designations",
    tags=["Designations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=APIResponse)
def list_designations(db: Session = Depends(get_db)):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    designations = service.get_all()
    return APIResponse(
        success=True,
        message="Designations retrieved successfully",
        data={"designations": [d.model_dump() for d in designations]},
    )


@router.get("/by-department/{department_id}", response_model=APIResponse)
def list_designations_by_department(
    department_id: uuid.UUID, db: Session = Depends(get_db)
):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    designations = service.get_by_department(department_id)
    return APIResponse(
        success=True,
        message="Designations retrieved successfully",
        data={"designations": [d.model_dump() for d in designations]},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_designation(
    designation_in: DesignationCreate, db: Session = Depends(get_db)
):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    try:
        designation = service.create(designation_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return APIResponse(
        success=True,
        message="Designation created successfully",
        data={"designation": designation.model_dump()},
    )


@router.get("/{id}", response_model=APIResponse)
def get_designation(id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    try:
        designation = service.get_by_id(id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found"
        )
    return APIResponse(
        success=True,
        message="Designation retrieved successfully",
        data={"designation": designation.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse)
def update_designation(
    id: uuid.UUID, designation_in: DesignationUpdate, db: Session = Depends(get_db)
):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    try:
        designation = service.update(id, designation_in)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return APIResponse(
        success=True,
        message="Designation updated successfully",
        data={"designation": designation.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse)
def delete_designation(id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services.designation_service import DesignationService

    service = DesignationService(db)
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Designation deleted successfully",
        data=None,
    )
