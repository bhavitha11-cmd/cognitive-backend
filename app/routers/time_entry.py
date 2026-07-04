import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.core.rbac import UserContext, require_data_access, DataAccessLevel
from app.schemas.common import APIResponse
from app.schemas.time_entry import (
    RejectTimeEntryRequest,
    TimeEntryCreate,
    TimeEntryCreateBatch,
    TimeEntryUpdate,
)
from app.services.time_entry_service import TimeEntryService

router = APIRouter(
    prefix="/time-entries",
    tags=["Time Entries"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> TimeEntryService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return TimeEntryService(db, current_user_id=uid)


# ── List ───────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
)
def list_time_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    employee_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    service: TimeEntryService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
):
    # SELF-level users can only list their own time entries
    if user_ctx.data_access_level == DataAccessLevel.SELF:
        employee_id = user_ctx.employee_id

    entries, total = service.get_all(
        skip=skip,
        limit=limit,
        employee_id=employee_id,
        task_id=task_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
    return APIResponse(
        success=True,
        message="Time entries retrieved successfully",
        data={
            "time_entries": [e.model_dump() for e in entries],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


# ── Create ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_time_entry(
    data: TimeEntryCreate,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        entry = service.create(data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entry created successfully",
        data={"time_entry": entry.model_dump()},
    )


# ── Batch create ────────────────────────────────────────────────────────────────

@router.post("/batch", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def batch_create_time_entries(
    data: TimeEntryCreateBatch,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        entries = service.create_batch(data.entries)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entries created successfully",
        data={"time_entries": [e.model_dump() for e in entries]},
    )


# ── My timesheet summary ───────────────────────────────────────────────────────

@router.get("/my-timesheet", response_model=APIResponse)
def get_my_timesheet(
    date_from: date = Query(...),
    date_to: date = Query(...),
    service: TimeEntryService = Depends(_get_service),
):
    try:
        summary = service.get_my_timesheet(date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Timesheet summary retrieved successfully",
        data={"summary": summary.model_dump()},
    )


# ── Employee timesheet summary ─────────────────────────────────────────────────

@router.get(
    "/summary/{employee_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Timesheets", "view"))],
)
def get_employee_timesheet_summary(
    employee_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    service: TimeEntryService = Depends(_get_service),
):
    try:
        summary = service.get_timesheet_summary(employee_id, date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Timesheet summary retrieved successfully",
        data={"summary": summary.model_dump()},
    )


# ── Get by ID ──────────────────────────────────────────────────────────────────

@router.get("/{id}", response_model=APIResponse)
def get_time_entry(
    id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    svc = TimeEntryService(db, current_user_id=uid)
    try:
        entry = svc.get_by_id(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Only the owner can view a specific time entry; managers use the list endpoint
    if entry.employee_id != uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own time entries",
        )

    return APIResponse(
        success=True,
        message="Time entry retrieved successfully",
        data={"time_entry": entry.model_dump()},
    )


# ── Update ─────────────────────────────────────────────────────────────────────

@router.put("/{id}", response_model=APIResponse)
def update_time_entry(
    id: uuid.UUID,
    data: TimeEntryUpdate,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        entry = service.update(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entry updated successfully",
        data={"time_entry": entry.model_dump()},
    )


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/{id}", response_model=APIResponse)
def delete_time_entry(
    id: uuid.UUID,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        service.delete(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Time entry deleted successfully")


# ── Submit ─────────────────────────────────────────────────────────────────────

@router.post("/{id}/submit", response_model=APIResponse)
def submit_time_entry(
    id: uuid.UUID,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        entry = service.submit(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entry submitted for approval",
        data={"time_entry": entry.model_dump()},
    )


# ── Approve ────────────────────────────────────────────────────────────────────

@router.post(
    "/{id}/approve",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Timesheets", "edit"))],
)
def approve_time_entry(
    id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    svc = TimeEntryService(db, current_user_id=uid)
    try:
        entry = svc.approve(id, uid)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entry approved",
        data={"time_entry": entry.model_dump()},
    )


# ── Reject ─────────────────────────────────────────────────────────────────────

@router.post(
    "/{id}/reject",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Timesheets", "edit"))],
)
def reject_time_entry(
    id: uuid.UUID,
    body: RejectTimeEntryRequest,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    svc = TimeEntryService(db, current_user_id=uid)
    try:
        entry = svc.reject(id, body.reason, uid)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Time entry rejected",
        data={"time_entry": entry.model_dump()},
    )


# ── Batch Weekly Submit/Approve/Reject Endpoints ──────────────────────────────

from pydantic import BaseModel

class BatchSubmitWeekRequest(BaseModel):
    date_from: date
    date_to: date

class BatchApproveWeekRequest(BaseModel):
    employee_id: uuid.UUID
    date_from: date
    date_to: date

class BatchRejectWeekRequest(BaseModel):
    employee_id: uuid.UUID
    date_from: date
    date_to: date
    reason: str | None = None


@router.post("/submit-week", response_model=APIResponse)
def submit_week(
    body: BatchSubmitWeekRequest,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        count = service.submit_week(body.date_from, body.date_to)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Submitted {count} time entries for the week",
        data={"count": count}
    )

@router.post(
    "/approve-week",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Timesheets", "edit"))],
)
def approve_week(
    body: BatchApproveWeekRequest,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        count = service.approve_week(body.employee_id, body.date_from, body.date_to)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Approved {count} time entries for the week",
        data={"count": count}
    )

@router.post(
    "/reject-week",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Timesheets", "edit"))],
)
def reject_week(
    body: BatchRejectWeekRequest,
    service: TimeEntryService = Depends(_get_service),
):
    try:
        count = service.reject_week(body.employee_id, body.date_from, body.date_to, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Rejected {count} time entries for the week",
        data={"count": count}
    )
