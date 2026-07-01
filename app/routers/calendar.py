from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.services.working_day_engine import WorkingDayEngine

VALID_EVENT_TYPES = {"holiday", "birthday", "anniversary", "company_event", "leave", "task_deadline", "task", "project"}

router = APIRouter(
    prefix="/calendar",
    tags=["Calendar"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.calendar_service import CalendarService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return CalendarService(db, current_user_id=uid)


@router.get(
    "/events",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Calendar", "view"))],
)
def get_calendar_events(
    from_date: date = Query(...),
    to_date: date = Query(...),
    types: str | None = Query(None, description="Comma-separated: holiday,birthday,task,project,company_event"),
    service=Depends(_get_service),
):
    if to_date < from_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end date must be after start date",
        )
    if (to_date - from_date).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date range cannot exceed 366 days",
        )
    type_list = None
    if types:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        invalid = set(type_list) - VALID_EVENT_TYPES
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown event types: {invalid}. Valid types: {sorted(VALID_EVENT_TYPES)}",
            )
    events = service.get_events(from_date, to_date, type_list)
    return APIResponse(
        success=True,
        message="Calendar events retrieved",
        data={"events": [e.model_dump(mode="json") for e in events]},
    )


@router.get(
    "/working-days",
    response_model=APIResponse,
)
def count_working_days(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
):
    count = WorkingDayEngine.count_working_days(start, end, db)
    return APIResponse(
        success=True,
        message="Working days counted",
        data={"count": count, "start": start.isoformat(), "end": end.isoformat()},
    )


@router.get(
    "/end-date",
    response_model=APIResponse,
)
def calculate_end_date(
    start: date = Query(...),
    hours: float = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    end = WorkingDayEngine.calculate_end_date(start, hours, db)
    return APIResponse(
        success=True,
        message="End date calculated",
        data={"start": start.isoformat(), "hours": hours, "end_date": end.isoformat()},
    )


@router.get(
    "/check-working-day",
    response_model=APIResponse,
)
def check_working_day(
    date_param: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    is_working = WorkingDayEngine.is_working_day(date_param, db)
    return APIResponse(
        success=True,
        message="Working day check completed",
        data={
            "date": date_param.isoformat(),
            "is_working_day": is_working,
            "is_weekend": WorkingDayEngine.is_weekend(date_param, db),
            "is_holiday": WorkingDayEngine.is_holiday(date_param, db),
        },
    )
