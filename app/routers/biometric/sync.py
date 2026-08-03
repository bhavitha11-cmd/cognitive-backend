from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.schemas.biometric.sync import (
    BmSyncTriggerRequest,
    BmSyncConfigUpdate,
    BmSyncConfigResponse
)

router = APIRouter(prefix="/sync", tags=["Biometric Sync"])

@router.post("/{device_id}")
def trigger_sync(
    device_id: uuid.UUID,
    payload: BmSyncTriggerRequest = BmSyncTriggerRequest(),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    try:
        uid = uuid.UUID(current_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user")
    
    from app.services.biometric.sync_engine import SyncEngine
    engine = SyncEngine(db)
    result = engine.run_sync(
        device_id=device_id,
        sync_type=payload.sync_type,
        from_dt=payload.from_datetime,
        to_dt=payload.to_datetime,
        triggered_by=uid,
    )
    return {
        "success": True,
        "data": {
            "sync_history_id": str(result.sync_history_id),
            "status": result.status,
            "records_read": result.records_read,
            "records_saved": result.records_saved,
            "duplicates_found": result.duplicates_found,
            "normalized_count": result.normalized_count,
            "duration_seconds": result.duration_seconds,
            "message": f"Sync completed: {result.status}",
        }
    }

@router.post("/all")
def trigger_sync_all(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    try:
        uid = uuid.UUID(current_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user")

    from app.services.biometric.sync_engine import SyncEngine
    engine = SyncEngine(db)
    result = engine.run_sync_all(triggered_by=uid)
    return {
        "success": True,
        "data": result
    }

@router.get("/config/{device_id}", response_model=BmSyncConfigResponse)
def get_sync_config(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.services.biometric.sync_config_service import SyncConfigService
    svc = SyncConfigService(db)
    config = svc.get_config(device_id)
    if not config:
        raise HTTPException(status_code=404, detail="Sync config not found")
    return config

@router.put("/config/{device_id}", response_model=BmSyncConfigResponse)
def update_sync_config(
    device_id: uuid.UUID,
    payload: BmSyncConfigUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.services.biometric.sync_config_service import SyncConfigService
    svc = SyncConfigService(db)
    try:
        config = svc.update_config(device_id, payload.model_dump(exclude_unset=True))
        if not config:
            raise HTTPException(status_code=404, detail="Sync config not found")
        return config
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
def get_sync_history(
    device_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.services.biometric.sync_history_service import SyncHistoryService
    svc = SyncHistoryService(db)
    history, total = svc.list_history(device_id=device_id, page=page, page_size=page_size)
    return {
        "success": True,
        "data": {
            "history": history,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    }


@router.post("/{history_id}/retry")
def retry_sync(
    history_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    try:
        uid = uuid.UUID(current_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user")

    from app.services.biometric.sync_history_service import SyncHistoryService
    from app.services.biometric.sync_engine import SyncEngine
    svc = SyncHistoryService(db)
    engine = SyncEngine(db)
    try:
        result = svc.retry_failed_sync(history_id, engine)
        return {
            "success": True,
            "data": {
                "sync_history_id": str(result.sync_history_id),
                "status": result.status,
                "records_read": result.records_read,
                "records_saved": result.records_saved,
                "message": f"Retry sync completed: {result.status}"
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

