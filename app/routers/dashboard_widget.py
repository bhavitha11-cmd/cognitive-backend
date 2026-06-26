from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.dashboard_widget_service import DashboardWidgetService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return DashboardWidgetService(db, current_user_id=uid)


@router.get(
    "/today-events",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def today_events(service=Depends(_get_service)):
    events = service.get_today_events()
    return APIResponse(
        success=True,
        message="Today's events retrieved",
        data={"events": [e.model_dump() for e in events]},
    )


@router.get(
    "/today-birthdays",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def today_birthdays(service=Depends(_get_service)):
    birthdays = service.get_today_birthdays()
    return APIResponse(
        success=True,
        message="Today's birthdays retrieved",
        data={"birthdays": [b.model_dump() for b in birthdays]},
    )


@router.get(
    "/upcoming-holidays",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def upcoming_holidays(
    days: int = Query(30, ge=1, le=365),
    service=Depends(_get_service),
):
    holidays = service.get_upcoming_holidays(days)
    return APIResponse(
        success=True,
        message="Upcoming holidays retrieved",
        data={"holidays": [h.model_dump() for h in holidays]},
    )


@router.get(
    "/upcoming-birthdays",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def upcoming_birthdays(
    days: int = Query(7, ge=1, le=365),
    service=Depends(_get_service),
):
    birthdays = service.get_upcoming_birthdays(days)
    return APIResponse(
        success=True,
        message="Upcoming birthdays retrieved",
        data={"birthdays": [b.model_dump() for b in birthdays]},
    )


@router.get(
    "/today-tasks",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def today_tasks(service=Depends(_get_service)):
    tasks = service.get_today_tasks()
    return APIResponse(
        success=True,
        message="Today's tasks retrieved",
        data={"tasks": [t.model_dump() for t in tasks]},
    )


@router.get(
    "/project-deliveries",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def project_deliveries(
    days: int = Query(30, ge=1, le=365),
    service=Depends(_get_service),
):
    projects = service.get_project_deliveries(days)
    return APIResponse(
        success=True,
        message="Project deliveries retrieved",
        data={"projects": [p.model_dump() for p in projects]},
    )


@router.get(
    "/delayed-tasks",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Dashboard", "view"))],
)
def delayed_tasks(service=Depends(_get_service)):
    tasks = service.get_delayed_tasks()
    return APIResponse(
        success=True,
        message="Delayed tasks retrieved",
        data={"tasks": [t.model_dump() for t in tasks]},
    )
