import uuid
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.services.biometric.biometric_log_service import BiometricLogService

router = APIRouter(prefix="/logs", tags=["Biometric Logs"])


def _get_service(db: Session = Depends(get_db)) -> BiometricLogService:
    return BiometricLogService(db)


@router.get("")
def list_normalized_logs(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    organization_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    device_id: Optional[uuid.UUID] = None,
    punch_type: Optional[str] = None,
    verification_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _=Depends(get_current_user),
    svc: BiometricLogService = Depends(_get_service),
):
    filters = {
        "from_date": from_date,
        "to_date": to_date,
        "organization_id": organization_id,
        "department_id": department_id,
        "employee_id": employee_id,
        "device_id": device_id,
        "punch_type": punch_type,
        "verification_type": verification_type,
    }
    logs, total = svc.list_normalized_logs(
        filters=filters,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": {"logs": logs, "total": total, "page": page, "page_size": page_size}}


@router.get("/export")
def export_logs(
    format: str = Query("csv"),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    organization_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    device_id: Optional[uuid.UUID] = None,
    punch_type: Optional[str] = None,
    verification_type: Optional[str] = None,
    _=Depends(get_current_user),
    svc: BiometricLogService = Depends(_get_service),
):
    filters = {
        "from_date": from_date,
        "to_date": to_date,
        "organization_id": organization_id,
        "department_id": department_id,
        "employee_id": employee_id,
        "device_id": device_id,
        "punch_type": punch_type,
        "verification_type": verification_type,
    }
    content = svc.export_logs_csv(filters=filters)
    headers = {"Content-Disposition": f"attachment; filename=biometric_logs.csv"}
    return Response(content=content, media_type="text/csv", headers=headers)


@router.get("/raw")
def list_raw_logs(
    device_id: Optional[uuid.UUID] = None,
    sync_history_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _=Depends(get_current_user),
    svc: BiometricLogService = Depends(_get_service),
):
    filters = {
        "device_id": device_id,
        "sync_history_id": sync_history_id,
    }
    logs, total = svc.list_raw_logs(
        filters=filters,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": {"logs": logs, "total": total, "page": page, "page_size": page_size}}
