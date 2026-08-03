import uuid
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.dependencies import get_current_user
from app.services.biometric.live_attendance_service import LiveAttendanceService

router = APIRouter(prefix="/live", tags=["Biometric Live Attendance"])

def _get_service(db=Depends(get_db)):
    return LiveAttendanceService(db)

@router.get("")
def get_live_attendance(
    response: Response,
    target_date: Optional[date] = Query(None),
    organization_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    branch: Optional[str] = None,
    _=Depends(get_current_user),
    svc: LiveAttendanceService = Depends(_get_service),
):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    records = svc.get_live_attendance(
        target_date=target_date,
        organization_id=organization_id,
        department_id=department_id,
        branch=branch,
    )
    return records
