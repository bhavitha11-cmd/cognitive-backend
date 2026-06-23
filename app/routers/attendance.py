import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.core.rbac import UserContext, require_data_access, DataAccessLevel
from app.schemas.attendance import AttendanceMarkRequest, AttendanceBulkMarkRequest, AttendanceRuleUpdate
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
    dependencies=[Depends(get_current_user)],
)


# ── Service factory ───────────────────────────────────────────────────────────

def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.attendance_service import AttendanceService

    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return AttendanceService(db, current_user_id=uid)


# ── Helper: resolve current employee id from user ─────────────────────────────

def _resolve_employee_id(current_user_id: str, db: Session) -> uuid.UUID:
    """The JWT sub is the employee.id directly in this platform."""
    try:
        return uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: cannot determine employee identity",
        )


# ── Optional clock-in body ────────────────────────────────────────────────────

class ClockInBody(BaseModel):
    notes: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/rules", response_model=APIResponse)
def get_attendance_rules(service=Depends(_get_service)):
    rule = service.get_rule()
    return APIResponse(
        success=True,
        message="Attendance rules retrieved successfully",
        data={"rule": rule.model_dump()},
    )


@router.put(
    "/rules",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Attendance", "edit"))],
)
def update_attendance_rules(
    rule_in: AttendanceRuleUpdate,
    service=Depends(_get_service),
):
    try:
        rule = service.update_rule(rule_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Attendance rules updated successfully",
        data={"rule": rule.model_dump()},
    )


@router.post("/clock-in", response_model=APIResponse)
def clock_in(
    body: ClockInBody = ClockInBody(),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
    service=Depends(_get_service),
):
    employee_id = _resolve_employee_id(current_user_id, db)
    try:
        record = service.clock_in(employee_id, notes=body.notes)
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    return APIResponse(
        success=True,
        message="Clock-in recorded successfully",
        data={"attendance": record.model_dump()},
    )


@router.post("/clock-out", response_model=APIResponse)
def clock_out(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
    service=Depends(_get_service),
):
    employee_id = _resolve_employee_id(current_user_id, db)
    try:
        record = service.clock_out(employee_id)

        # Rule 7: Auto-close any running work session on clock-out
        from app.services.work_session_service import WorkSessionService
        ws_service = WorkSessionService(db, current_user_id=employee_id)
        closed_session_id = ws_service.end_current_session_on_clock_out()
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    return APIResponse(
        success=True,
        message="Clock-out recorded successfully",
        data={
            "attendance": record.model_dump(),
            "auto_closed_session": str(closed_session_id) if closed_session_id else None,
        },
    )


@router.post(
    "/mark",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("Attendance", "edit"))],
)
def mark_attendance(
    attendance_in: AttendanceMarkRequest,
    service=Depends(_get_service),
):
    try:
        record = service.mark_attendance(attendance_in)
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    return APIResponse(
        success=True,
        message="Attendance marked successfully",
        data={"attendance": record.model_dump()},
    )


@router.get(
    "",
    response_model=APIResponse,
)
def list_attendance(
    employee_id: Optional[uuid.UUID] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    record_date: Optional[date] = Query(None, alias="date"),
    department_id: Optional[uuid.UUID] = Query(None),
    service=Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    """
    Flexible list endpoint:
    - ?employee_id=<uuid> [&from_date=YYYY-MM-DD] [&to_date=YYYY-MM-DD]  — records for one employee
    - ?date=YYYY-MM-DD [&department_id=<uuid>]                            — all employees on a date
    """
    # SELF-level users can only see their own attendance records
    if user_ctx.data_access_level == DataAccessLevel.SELF:
        employee_id = user_ctx.employee_id
        department_id = None  # dept filter irrelevant for self-view

    try:
        if employee_id:
            records = service.get_by_employee(employee_id, from_date, to_date)
        elif record_date:
            records = service.get_by_date(record_date, department_id)
        else:
            # Default: today's attendance, optionally filtered by department
            from datetime import date as _date
            records = service.get_by_date(_date.today(), department_id)
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)

    return APIResponse(
        success=True,
        message="Attendance records retrieved successfully",
        data={
            "attendance": [r.model_dump() for r in records],
            "total": len(records),
        },
    )


@router.get(
    "/summary/{employee_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Attendance", "view"))],
)
def get_attendance_summary(
    employee_id: uuid.UUID,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    service=Depends(_get_service),
):
    try:
        summary = service.get_summary(employee_id, year, month)
    except ValueError as e:
        detail = str(e)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    return APIResponse(
        success=True,
        message="Attendance summary retrieved successfully",
        data={"summary": summary},
    )


@router.get("/me", response_model=APIResponse)
def get_my_attendance(
    record_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
    service=Depends(_get_service),
):
    employee_id = _resolve_employee_id(current_user_id, db)
    records = service.get_by_employee(employee_id, record_date, record_date)
    record = records[0] if records else None
    return APIResponse(
        success=True,
        message="My attendance retrieved successfully",
        data={"attendance": record.model_dump() if record else None},
    )


@router.get(
    "/today",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Attendance", "view"))],
)
def get_today_attendance(
    department_id: Optional[uuid.UUID] = Query(None),
    service=Depends(_get_service),
):
    from datetime import date as _date

    records = service.get_by_date(_date.today(), department_id)
    return APIResponse(
        success=True,
        message="Today's attendance retrieved successfully",
        data={
            "attendance": [r.model_dump() for r in records],
            "total": len(records),
            "date": str(_date.today()),
        },
    )
