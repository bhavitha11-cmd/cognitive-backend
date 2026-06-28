from __future__ import annotations

import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.task_continuity import ManagerDecisionCreate
from app.services.task_continuity_service import TaskContinuityService
from app.services.dashboard_widget_service import DashboardWidgetService

router = APIRouter(
    prefix="/task-continuity",
    tags=["Task Continuity Engine"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> TaskContinuityService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )
    return TaskContinuityService(db, current_user_id=uid)


def _get_widget_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> DashboardWidgetService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )
    return DashboardWidgetService(db, current_user_id=uid)


@router.get("/risks", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "view"))])
def list_task_risks(
    status_filter: Optional[str] = Query(None, alias="status"),
    service: TaskContinuityService = Depends(_get_service),
):
    risks = service.repo.get_all_risks(status=status_filter)
    serialized = []
    for r in risks:
        serialized.append(
            {
                "id": str(r.id),
                "task_id": str(r.task_id),
                "task_title": r.task.title if r.task else None,
                "task_code": r.task.task_code if r.task else None,
                "project_id": str(r.project_id),
                "project_name": r.project.name if r.project else None,
                "assignment_id": str(r.assignment_id),
                "employee_id": str(r.employee_id),
                "employee_name": f"{r.employee.first_name} {r.employee.last_name or ''}".strip()
                if r.employee
                else None,
                "leave_request_id": str(r.leave_request_id),
                "leave_start_date": r.leave_start_date,
                "leave_end_date": r.leave_end_date,
                "remaining_hours": float(r.remaining_hours),
                "risk_level": r.risk_level,
                "days_impacted": r.days_impacted,
                "project_impact": r.project_impact,
                "status": r.status,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
        )
    return APIResponse(
        success=True,
        message="Task risks retrieved successfully",
        data={"risks": serialized, "total": len(serialized)},
    )


@router.post("/risks/{risk_id}/resolve", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "edit"))])
def resolve_task_risk(
    risk_id: uuid.UUID,
    decision_data: ManagerDecisionCreate,
    current_user_id: str = Depends(get_current_user),
    service: TaskContinuityService = Depends(_get_service),
):
    try:
        manager_id = uuid.UUID(current_user_id)
        decision = service.resolve_task_risk(risk_id, manager_id, decision_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    return APIResponse(
        success=True,
        message="Manager decision processed successfully",
        data={
            "decision": {
                "id": str(decision.id),
                "task_risk_id": str(decision.task_risk_id),
                "task_id": str(decision.task_id),
                "manager_id": str(decision.manager_id)
                if decision.manager_id
                else None,
                "decision": decision.decision,
                "details": decision.details,
                "decided_at": decision.decided_at,
            }
        },
    )


@router.post("/delegations/{delegation_id}/resume", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "edit"))])
def resume_delegated_task(
    delegation_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    service: TaskContinuityService = Depends(_get_service),
):
    try:
        manager_id = uuid.UUID(current_user_id)
        service.resume_delegated_task(delegation_id, manager_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Delegation ended and task reverted to original owner successfully",
    )


@router.post("/tasks/{task_id}/resume", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "edit"))])
def resume_paused_task(
    task_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user),
    service: TaskContinuityService = Depends(_get_service),
):
    try:
        manager_id = uuid.UUID(current_user_id)
        service.resume_paused_task(task_id, manager_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Paused task resumed successfully",
    )


@router.get("/dashboard/reassignments", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "view"))])
def get_tasks_requiring_reassignment(
    service: DashboardWidgetService = Depends(_get_widget_service),
):
    results = service.get_tasks_requiring_reassignment()
    return APIResponse(
        success=True,
        message="Tasks requiring reassignment retrieved successfully",
        data={"tasks": results, "total": len(results)},
    )


@router.get("/dashboard/kpis", response_model=APIResponse, dependencies=[Depends(require_permission("Tasks", "view"))])
def get_continuity_dashboard_kpis(
    service: DashboardWidgetService = Depends(_get_widget_service),
):
    results = service.get_continuity_dashboard_kpis()
    return APIResponse(
        success=True,
        message="Task continuity KPIs retrieved successfully",
        data=results,
    )
