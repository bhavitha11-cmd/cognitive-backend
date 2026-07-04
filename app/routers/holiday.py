from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.holiday import (
    HolidayCreate,
    HolidayResponse,
    HolidayUpdate,
    EmergencyHolidayImpactResponse,
    EmergencyHolidayApplyRequest,
)

router = APIRouter(
    prefix="/holidays",
    tags=["Holidays"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.holiday_service import HolidayService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )
    return HolidayService(db, current_user_id=uid)


@router.get(
    "/upcoming",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "view"))],
)
def get_upcoming_holidays(
    days: int = Query(30, ge=1, le=365),
    service=Depends(_get_service),
):
    holidays = service.get_upcoming(days)
    return APIResponse(
        success=True,
        message="Upcoming holidays retrieved",
        data={"holidays": [h.model_dump(mode="json") for h in holidays]},
    )


@router.get(
    "/check",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "view"))],
)
def check_holiday_date(
    date_param: date = Query(..., alias="date"),
    service=Depends(_get_service),
):
    holiday = service.check_date(date_param)
    return APIResponse(
        success=True,
        message="Holiday check completed",
        data={
            "is_holiday": holiday is not None,
            "holiday": holiday.model_dump(mode="json") if holiday else None,
        },
    )


VALID_SORT_COLUMNS = {"date", "name", "holiday_type", "created_at"}


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "view"))],
)
def list_holidays(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    year: int | None = Query(None),
    holiday_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    sort_by: str = Query("date"),
    sort_order: str = Query("asc"),
    service=Depends(_get_service),
):
    if sort_by not in VALID_SORT_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort_by must be one of {sorted(VALID_SORT_COLUMNS)}",
        )
    if sort_order.lower() not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sort_order must be 'asc' or 'desc'",
        )
    sort_order = sort_order.lower()
    items, total = service.get_all(
        skip=skip,
        limit=limit,
        year=year,
        holiday_type=holiday_type,
        is_active=is_active,
        search=search,
        from_date=from_date,
        to_date=to_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return APIResponse(
        success=True,
        message="Holidays retrieved",
        data={
            "holidays": [h.model_dump(mode="json") for h in items],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "view"))],
)
def get_holiday(
    id: uuid.UUID,
    service=Depends(_get_service),
):
    try:
        holiday = service.get_by_id(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Holiday retrieved",
        data={"holiday": holiday.model_dump(mode="json")},
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Holiday", "create"))],
)
def create_holiday(
    data: HolidayCreate,
    service=Depends(_get_service),
):
    try:
        holiday = service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Holiday created",
        data={"holiday": holiday.model_dump(mode="json")},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "edit"))],
)
def update_holiday(
    id: uuid.UUID,
    data: HolidayUpdate,
    service=Depends(_get_service),
):
    try:
        holiday = service.update(id, data)
    except ValueError as e:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))
    return APIResponse(
        success=True,
        message="Holiday updated",
        data={"holiday": holiday.model_dump(mode="json")},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "activate"))],
)
def delete_holiday(
    id: uuid.UUID,
    service=Depends(_get_service),
):
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Holiday deactivated",
    )


@router.patch(
    "/{id}/toggle",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "edit"))],
)
def toggle_holiday(
    id: uuid.UUID,
    service=Depends(_get_service),
):
    try:
        holiday = service.toggle_active(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Holiday {'activated' if holiday.is_active else 'deactivated'}",
        data={"holiday": holiday.model_dump(mode="json")},
    )


@router.get(
    "/emergency/{id}/impact-analysis",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "view"))],
)
def get_emergency_holiday_impact(
    id: uuid.UUID,
    service=Depends(_get_service),
):
    try:
        impact = service.get_impact_analysis(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Emergency holiday impact analysis generated",
        data=impact,
    )


@router.post(
    "/emergency/{id}/apply",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "edit"))],
)
def apply_emergency_holiday(
    id: uuid.UUID,
    data: EmergencyHolidayApplyRequest,
    service=Depends(_get_service),
):
    try:
        result = service.apply_emergency_holiday(id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=result["message"],
    )


@router.post(
    "/emergency/{id}/reject",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Holiday", "edit"))],
)
def reject_emergency_holiday(
    id: uuid.UUID,
    service=Depends(_get_service),
):
    try:
        result = service.reject_emergency_holiday(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message=result["message"],
    )
