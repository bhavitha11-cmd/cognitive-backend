import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.designation import DesignationCreate, DesignationUpdate
from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/designations",
    tags=["Designations"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user)):
    from app.services.designation_service import DesignationService
    from uuid import UUID
    try:
        uid = UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return DesignationService(db, current_user_id=uid)


@router.get("", response_model=APIResponse)
def list_designations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service=Depends(_get_service),
):
    designations, total = service.get_all(skip=skip, limit=limit)
    return APIResponse(
        success=True,
        message="Designations retrieved successfully",
        data={"designations": [d.model_dump() for d in designations], "total": total, "skip": skip, "limit": limit},
    )


@router.get("/by-department/{department_id}", response_model=APIResponse)
def list_designations_by_department(department_id: uuid.UUID, service=Depends(_get_service)):
    designations = service.get_by_department(department_id)
    return APIResponse(
        success=True,
        message="Designations retrieved successfully",
        data={"designations": [d.model_dump() for d in designations]},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("HR", "create"))])
def create_designation(designation_in: DesignationCreate, service=Depends(_get_service)):
    try:
        designation = service.create(designation_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Designation created successfully",
        data={"designation": designation.model_dump()},
    )


@router.get("/lookup", response_model=APIResponse)
def lookup_designations(service=Depends(_get_service)):
    designations = service.get_lookup()
    return APIResponse(
        success=True,
        message="Designations lookup retrieved successfully",
        data={"designations": [d.model_dump() for d in designations]},
    )


@router.get("/{id}", response_model=APIResponse)
def get_designation(id: uuid.UUID, service=Depends(_get_service)):
    try:
        designation = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found")
    return APIResponse(
        success=True,
        message="Designation retrieved successfully",
        data={"designation": designation.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "edit"))])
def update_designation(id: uuid.UUID, designation_in: DesignationUpdate, service=Depends(_get_service)):
    try:
        designation = service.update(id, designation_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Designation updated successfully",
        data={"designation": designation.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("HR", "activate"))])
def delete_designation(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Designation deleted successfully")
