import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.services.biometric.device_health_service import DeviceHealthService
from app.schemas.biometric.health import BmDeviceHealthResponse

router = APIRouter(prefix="/health", tags=["Biometric Device Health"])

def _get_service(db=Depends(get_db)):
    return DeviceHealthService(db)

@router.get("", response_model=List[BmDeviceHealthResponse])
def list_device_health(
    _=Depends(get_current_user),
    svc: DeviceHealthService = Depends(_get_service),
):
    health_records = svc.list_all_health()
    return health_records

@router.get("/{device_id}", response_model=BmDeviceHealthResponse)
def get_device_health(
    device_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: DeviceHealthService = Depends(_get_service),
):
    health = svc.get_device_health(device_id)
    if not health:
        raise HTTPException(status_code=404, detail="Device health not found")
    return health
