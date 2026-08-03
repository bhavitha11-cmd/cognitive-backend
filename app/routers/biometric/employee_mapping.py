import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.services.biometric.employee_mapping_service import EmployeeMappingService
from app.schemas.biometric.employee_mapping import (
    BmEmployeeMappingCreate,
    BmEmployeeMappingUpdate,
    BmEmployeeMappingResponse,
    BmEmployeeMappingListResponse,
    BmBulkMappingRequest,
    BmAutoMapRequest
)

router = APIRouter(prefix="/mappings", tags=["Biometric Employee Mapping"])

def _get_service(db=Depends(get_db)):
    return EmployeeMappingService(db)

@router.get("", response_model=BmEmployeeMappingListResponse)
def list_mappings(
    device_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    mappings, total = svc.list_mappings(
        device_id=device_id,
        employee_id=employee_id,
        page=page,
        page_size=page_size
    )
    return {"mappings": mappings, "total": total, "page": page, "page_size": page_size}

@router.post("", response_model=BmEmployeeMappingResponse, status_code=201)
def create_mapping(
    payload: BmEmployeeMappingCreate,
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    try:
        mapping = svc.create_mapping(payload.model_dump())
        return mapping
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/bulk", status_code=200)
def bulk_mapping(
    payload: BmBulkMappingRequest,
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    try:
        result = svc.bulk_import_mappings(payload.mappings)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auto", status_code=200)
def auto_map(
    payload: BmAutoMapRequest,
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    try:
        result = svc.auto_map_employees(payload.device_id, payload.match_by)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{mapping_id}", response_model=BmEmployeeMappingResponse)
def update_mapping(
    mapping_id: uuid.UUID,
    payload: BmEmployeeMappingUpdate,
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    try:
        mapping = svc.update_mapping(mapping_id, payload.model_dump(exclude_unset=True))
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")
        return mapping
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{mapping_id}", status_code=204)
def deactivate_mapping(
    mapping_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: EmployeeMappingService = Depends(_get_service),
):
    if not svc.deactivate_mapping(mapping_id):
        raise HTTPException(status_code=404, detail="Mapping not found")
