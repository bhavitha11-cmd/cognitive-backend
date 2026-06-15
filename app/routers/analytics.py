from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    dependencies=[Depends(get_current_user), Depends(require_permission("Analytics", "view"))],
)


def _get_service(db: Session = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


@router.get("/dashboard", response_model=APIResponse)
def dashboard_stats(service: AnalyticsService = Depends(_get_service)):
    stats = service.get_dashboard_stats()
    return APIResponse(success=True, message="Dashboard stats retrieved", data=stats.model_dump())


@router.get("/plan-vs-actual", response_model=APIResponse)
def plan_vs_actual(service: AnalyticsService = Depends(_get_service)):
    result = service.get_plan_vs_actual()
    return APIResponse(success=True, message="Plan vs actual data retrieved", data=result.model_dump())


@router.get("/utilization", response_model=APIResponse)
def utilization(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    service: AnalyticsService = Depends(_get_service),
):
    result = service.get_employee_utilization(from_date, to_date)
    return APIResponse(success=True, message="Utilization data retrieved", data=result.model_dump())


@router.get("/department-load", response_model=APIResponse)
def department_load(service: AnalyticsService = Depends(_get_service)):
    result = service.get_department_load()
    return APIResponse(success=True, message="Department load retrieved", data=result.model_dump())


@router.get("/overdue-tasks", response_model=APIResponse)
def overdue_tasks(service: AnalyticsService = Depends(_get_service)):
    result = service.get_overdue_tasks()
    return APIResponse(success=True, message="Overdue tasks retrieved", data={"tasks": [t.model_dump() for t in result]})


@router.get("/upcoming-deadlines", response_model=APIResponse)
def upcoming_deadlines(
    days: int = Query(14, ge=1, le=90),
    service: AnalyticsService = Depends(_get_service),
):
    result = service.get_upcoming_deadlines(days)
    return APIResponse(success=True, message="Upcoming deadlines retrieved", data={"tasks": [t.model_dump() for t in result]})


@router.get("/client-performance", response_model=APIResponse)
def client_performance(service: AnalyticsService = Depends(_get_service)):
    result = service.get_client_performance()
    return APIResponse(success=True, message="Client performance retrieved", data=result.model_dump())


@router.get("/scope-distribution", response_model=APIResponse)
def scope_distribution(service: AnalyticsService = Depends(_get_service)):
    result = service.get_scope_distribution()
    return APIResponse(success=True, message="Scope distribution retrieved", data=result.model_dump())


@router.get("/calendar-events", response_model=APIResponse)
def calendar_events(
    from_date: date = Query(...),
    to_date: date = Query(...),
    service: AnalyticsService = Depends(_get_service),
):
    result = service.get_calendar_events(from_date, to_date)
    return APIResponse(success=True, message="Calendar events retrieved", data={"events": result})
