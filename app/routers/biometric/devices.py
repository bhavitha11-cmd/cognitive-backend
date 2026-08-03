import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.services.biometric.device_service import DeviceService
from app.schemas.biometric.device import (
    BmDeviceCreate, BmDeviceUpdate, BmDeviceResponse, BmDeviceListResponse
)

router = APIRouter(prefix="/devices", tags=["Biometric Devices"])

def _get_service(db=Depends(get_db), current_user_id=Depends(get_current_user)):
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid user identity")
    return DeviceService(db, current_user_id=uid)

@router.get("", response_model=BmDeviceListResponse)
def list_devices(
    organization_id: Optional[uuid.UUID] = None,
    vendor: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _=Depends(get_current_user),
    svc: DeviceService = Depends(_get_service),
):
    devices, total = svc.list_devices(
        organization_id=organization_id,
        vendor=vendor,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {"devices": devices, "total": total, "page": page, "page_size": page_size}

@router.post("", response_model=BmDeviceResponse, status_code=201)
def create_device(
    payload: BmDeviceCreate,
    _=Depends(get_current_user),
    svc: DeviceService = Depends(_get_service),
):
    try:
        device = svc.create_device(payload.model_dump())
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create device: {e}")

@router.get("/{device_id}", response_model=BmDeviceResponse)
def get_device(
    device_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: DeviceService = Depends(_get_service),
):
    device = svc.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.put("/{device_id}", response_model=BmDeviceResponse)
def update_device(
    device_id: uuid.UUID,
    payload: BmDeviceUpdate,
    _=Depends(get_current_user),
    svc: DeviceService = Depends(_get_service),
):
    device = svc.update_device(device_id, payload.model_dump(exclude_none=True))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: DeviceService = Depends(_get_service),
):
    if not svc.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")


@router.get("/{device_id}/users")
def get_device_registered_users(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """
    Connects to the device and returns the list of registered users on it.
    """
    from app.services.biometric.connection_profile_service import ConnectionProfileService
    device_svc = DeviceService(db)
    profile_svc = ConnectionProfileService(db)
    
    device = device_svc.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    profile = profile_svc.get_profile_for_device(device_id)
    if not profile:
        raise HTTPException(status_code=422, detail="No active connection profile found for this device")
        
    from app.services.biometric.connectors.factory import ConnectorFactory
    from app.services.biometric.connection_profile_service import ConnectionProfileService
    try:
        connector = ConnectorFactory.get_connector(
            device.vendor,
            profile.connection_type,
            profile.config_encrypted,
        )
        with connector:
            users = connector.get_registered_users()
        return {"success": True, "data": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch users from device: {e}")

