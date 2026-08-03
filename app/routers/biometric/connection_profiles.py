import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.services.biometric.connection_profile_service import ConnectionProfileService
from app.schemas.biometric.connection_profile import (
    BmConnectionProfileCreate,
    BmConnectionProfileUpdate,
    BmConnectionProfileResponse
)

router = APIRouter(prefix="/connections", tags=["Biometric Connection Profiles"])

def _get_service(db=Depends(get_db)):
    return ConnectionProfileService(db)

@router.get("", response_model=List[BmConnectionProfileResponse])
def list_connection_profiles(
    device_id: Optional[uuid.UUID] = None,
    _=Depends(get_current_user),
    svc: ConnectionProfileService = Depends(_get_service),
):
    if device_id:
        profiles = svc.list_profiles(device_id)
        return profiles
    return []

@router.post("", response_model=BmConnectionProfileResponse, status_code=201)
def create_connection_profile(
    payload: BmConnectionProfileCreate,
    _=Depends(get_current_user),
    svc: ConnectionProfileService = Depends(_get_service),
):
    try:
        profile = svc.create_profile(
            device_id=payload.device_id,
            connection_type=payload.connection_type,
            config_dict=payload.config.model_dump()
        )
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {e}")

@router.get("/{profile_id}", response_model=BmConnectionProfileResponse)
def get_connection_profile(
    profile_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: ConnectionProfileService = Depends(_get_service),
):
    profile = svc.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@router.put("/{profile_id}", response_model=BmConnectionProfileResponse)
def update_connection_profile(
    profile_id: uuid.UUID,
    payload: BmConnectionProfileUpdate,
    _=Depends(get_current_user),
    svc: ConnectionProfileService = Depends(_get_service),
):
    try:
        update_data = {}
        if payload.config is not None:
            update_data["config_dict"] = payload.config.model_dump()
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active
            
        profile = svc.update_profile(profile_id, update_data)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{profile_id}", status_code=204)
def delete_connection_profile(
    profile_id: uuid.UUID,
    _=Depends(get_current_user),
    svc: ConnectionProfileService = Depends(_get_service),
):
    if not svc.delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
