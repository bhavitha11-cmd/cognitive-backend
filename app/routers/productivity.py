from datetime import date as date_type, datetime, timedelta, timezone
from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user
from app.core.rbac import UserContext, require_data_access, DataAccessLevel
from app.schemas.common import APIResponse
from app.schemas.productivity import (
    ProductivityKPIResponse,
    TimelineEventResponse,
    IdleReasonResponse,
    IdleClassificationCreate,
    IdleClassificationResponse,
    RangeProductivityResponse
)
from app.services.productivity.productivity_service import WorkforceProductivityService

router = APIRouter(
    prefix="/analytics/productivity",
    tags=["Workforce Productivity"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(require_data_access)
) -> WorkforceProductivityService:
    return WorkforceProductivityService(db, current_user_id=user_ctx.employee_id)


def _check_employee_access(employee_id: uuid.UUID, user_ctx: UserContext, db: Session):
    """Enforce that employees can view their own metrics; managers or admin can view others based on hierarchy."""
    from app.services.productivity.authorization_service import AuthorizationService
    AuthorizationService.verify_access(db, user_ctx.employee_id, employee_id, user_ctx)



@router.get("/today", response_model=APIResponse)
def get_today_productivity(
    service: WorkforceProductivityService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access)
):
    """Get today's productivity KPIs for the logged-in employee."""
    try:
        data = service.get_today_kpis(user_ctx.employee_id)
        return APIResponse(
            success=True,
            message="Today's productivity KPIs retrieved successfully",
            data=data
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to calculate today's KPIs: {str(e)}"
        )


@router.get("/employee/{employee_id}", response_model=APIResponse)
def get_employee_productivity(
    employee_id: uuid.UUID,
    from_date: Optional[date_type] = Query(None),
    to_date: Optional[date_type] = Query(None),
    service: WorkforceProductivityService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db)
):
    """Get productivity KPIs for a specific employee over a date range."""
    _check_employee_access(employee_id, user_ctx, db)

    if not to_date:
        to_date = datetime.now(timezone.utc).date()
    if not from_date:
        from_date = to_date - timedelta(days=30)

    try:
        data = service.get_employee_range_metrics(employee_id, from_date, to_date)
        return APIResponse(
            success=True,
            message="Employee range metrics retrieved successfully",
            data=data
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to retrieve range metrics: {str(e)}"
        )


@router.get("/timeline", response_model=APIResponse)
def get_employee_timeline(
    employee_id: Optional[uuid.UUID] = Query(None),
    query_date: Optional[date_type] = Query(None),
    service: WorkforceProductivityService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db)
):
    """Get chronological activity timeline for an employee on a specific date."""
    target_emp_id = employee_id or user_ctx.employee_id
    _check_employee_access(target_emp_id, user_ctx, db)

    target_date = query_date or datetime.now(timezone.utc).date()

    try:
        timeline = service.get_timeline(target_emp_id, target_date)
        return APIResponse(
            success=True,
            message="Timeline retrieved successfully",
            data={"timeline": timeline}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to rebuild timeline: {str(e)}"
        )


@router.get("/reasons", response_model=APIResponse)
def get_active_idle_reasons(
    department_id: Optional[uuid.UUID] = Query(None),
    service: WorkforceProductivityService = Depends(_get_service)
):
    """Retrieve list of active idle reasons for a department or global."""
    try:
        reasons = service.get_active_reasons(department_id)
        return APIResponse(
            success=True,
            message="Idle reasons retrieved successfully",
            data={"reasons": [IdleReasonResponse.model_validate(r).model_dump() for r in reasons]}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to load idle reasons: {str(e)}"
        )


@router.post("/idle-classifications", response_model=APIResponse)
def create_idle_classification(
    body: IdleClassificationCreate,
    service: WorkforceProductivityService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access)
):
    """Classify a dynamic idle time segment with a configured reason."""
    try:
        classification = service.classify_idle_segment(
            employee_id=user_ctx.employee_id,
            query_date=body.date,
            idle_segment_identifier=body.idle_segment_identifier,
            reason_id=body.reason_id,
            remarks=body.remarks
        )
        return APIResponse(
            success=True,
            message="Idle segment classified successfully",
            data={"classification": IdleClassificationResponse.model_validate(classification).model_dump()}
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal database error: {str(e)}"
        )


@router.get("/metrics", response_model=APIResponse)
def get_workforce_metrics_report(
    employee_ids: list[uuid.UUID] = Query(...),
    start_date: date_type = Query(...),
    end_date: date_type = Query(...),
    service: WorkforceProductivityService = Depends(_get_service),
    user_ctx: UserContext = Depends(require_data_access),
    db: Session = Depends(get_db)
):
    """Get aggregated workforce metrics report (Manager/Admin only)."""
    if user_ctx.data_access_level < DataAccessLevel.MANAGED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You do not have permission to view bulk workforce reports."
        )

    # Validate manager access to every employee ID in the bulk list
    for emp_id in employee_ids:
        _check_employee_access(emp_id, user_ctx, db)

    try:
        report = service.get_bulk_productivity_report(employee_ids, start_date, end_date)
        return APIResponse(
            success=True,
            message="Bulk workforce metrics report generated successfully",
            data={"report": report}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate report: {str(e)}"
        )
