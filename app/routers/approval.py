import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.approval import ApprovalInstance, ApprovalWorkflow
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.role import Role
from app.schemas.approval import (
    ApprovalActionRequest,
    ApprovalInstanceResponse,
    ApprovalWorkflowCreate,
    ApprovalWorkflowResponse,
    ApprovalWorkflowStepCreate,
    ApprovalWorkflowStepResponse,
)
from app.schemas.common import APIResponse
from app.services.approval_service import ApprovalService

router = APIRouter(
    prefix="/approvals",
    tags=["Approval Engine"],
    dependencies=[Depends(get_current_user)],
)


def _summarize_attendance_correction(
    service: ApprovalService, target_id: uuid.UUID
) -> tuple[str | None, str | None, str | None]:
    """Resolves (requester_name, requester_code, details_summary) for an
    ATTENDANCE_CORRECTION ApprovalInstance by looking up the underlying
    MissedClockinRequest or MissedClockoutRequest — module_type alone doesn't
    distinguish the two since they share one combined workflow."""
    from app.models.missed_clockin_request import MissedClockinRequest
    from app.models.missed_clockout_request import MissedClockoutRequest

    requester_name: str | None = None
    requester_code: str | None = None
    details_summary: str | None = None

    mc_in = service.db.get(MissedClockinRequest, target_id)
    if mc_in:
        emp = service.db.get(Employee, mc_in.employee_id)
        if emp:
            requester_name = f"{emp.first_name} {emp.last_name}"
            requester_code = emp.employee_code
        details_summary = (
            f"Missed Clock-in on {mc_in.attendance_date} — requested "
            f"{mc_in.requested_clock_in}. Reason: {mc_in.reason or 'No reason provided'}"
        )
        return requester_name, requester_code, details_summary

    mc_out = service.db.get(MissedClockoutRequest, target_id)
    if mc_out:
        emp = service.db.get(Employee, mc_out.employee_id)
        if emp:
            requester_name = f"{emp.first_name} {emp.last_name}"
            requester_code = emp.employee_code
        details_summary = (
            f"Missed Clock-out on {mc_out.attendance_date} — requested "
            f"{mc_out.requested_clock_out}. Reason: {mc_out.reason or 'No reason provided'}"
        )
    return requester_name, requester_code, details_summary


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> ApprovalService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity"
        )
    return ApprovalService(db, current_user_id=uid)


# ── Workflow Settings (Admin Only) ────────────────────────────────────────────


@router.get(
    "/workflows",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "view"))],
)
def list_workflows(
    module_type: str | None = None,
    service: ApprovalService = Depends(_get_service),
):
    workflows = service.get_all_workflows(module_type=module_type)
    result = []
    for wf in workflows:
        steps_resp = []
        for step in wf.steps:
            req_role = service.db.get(Role, step.requester_role_id)
            app_role = service.db.get(Role, step.approver_role_id)
            steps_resp.append(
                ApprovalWorkflowStepResponse(
                    id=step.id,
                    workflow_id=step.workflow_id,
                    requester_role_id=step.requester_role_id,
                    requester_role_name=req_role.name if req_role else None,
                    level=step.level,
                    approver_role_id=step.approver_role_id,
                    approver_role_name=app_role.name if app_role else None,
                    resolution_scope=step.resolution_scope,
                )
            )
        wf_resp = ApprovalWorkflowResponse(
            id=wf.id,
            name=wf.name,
            module_type=wf.module_type,
            version=wf.version,
            approval_strategy=wf.approval_strategy,
            is_active=wf.is_active,
            created_at=wf.created_at,
            updated_at=wf.updated_at,
            steps=steps_resp,
        )
        result.append(wf_resp.model_dump())

    return APIResponse(
        success=True,
        message="Workflows retrieved successfully",
        data={"workflows": result},
    )


@router.post(
    "/workflows",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def create_workflow(
    data: ApprovalWorkflowCreate,
    service: ApprovalService = Depends(_get_service),
):
    try:
        wf = service.create_workflow(
            name=data.name,
            module_type=data.module_type,
            approval_strategy=data.approval_strategy,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Workflow created successfully",
        data={
            "workflow": {
                "id": str(wf.id),
                "name": wf.name,
                "module_type": wf.module_type,
                "version": wf.version,
                "approval_strategy": wf.approval_strategy,
                "is_active": wf.is_active,
            }
        },
    )


@router.post(
    "/workflows/{id}/steps",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def configure_workflow_steps(
    id: uuid.UUID,
    steps: list[ApprovalWorkflowStepCreate],
    service: ApprovalService = Depends(_get_service),
):
    steps_dict_list = [step.model_dump() for step in steps]
    try:
        updated_steps = service.set_workflow_steps(id, steps_dict_list)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    steps_resp = []
    for step in updated_steps:
        req_role = service.db.get(Role, step.requester_role_id)
        app_role = service.db.get(Role, step.approver_role_id)
        steps_resp.append(
            ApprovalWorkflowStepResponse(
                id=step.id,
                workflow_id=step.workflow_id,
                requester_role_id=step.requester_role_id,
                requester_role_name=req_role.name if req_role else None,
                level=step.level,
                approver_role_id=step.approver_role_id,
                approver_role_name=app_role.name if app_role else None,
                resolution_scope=step.resolution_scope,
            ).model_dump()
        )

    return APIResponse(
        success=True,
        message="Workflow steps updated successfully",
        data={"steps": steps_resp},
    )


@router.put(
    "/workflows/{id}/activate",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Settings", "edit"))],
)
def activate_workflow(
    id: uuid.UUID,
    service: ApprovalService = Depends(_get_service),
):
    try:
        wf = service.activate_workflow(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Workflow activated successfully",
        data={
            "workflow": {
                "id": str(wf.id),
                "name": wf.name,
                "module_type": wf.module_type,
                "version": wf.version,
                "is_active": wf.is_active,
            }
        },
    )


# ── Action Pending Approvals & Processes ──────────────────────────────────────


@router.get("/pending", response_model=APIResponse)
def get_pending_approvals(
    service: ApprovalService = Depends(_get_service),
):
    user_id = service.current_user_id
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User session not identified"
        )

    pending_instances = service.get_pending_approvals(user_id)
    result = []

    for inst in pending_instances:
        # Resolve target details dynamically to show rich UI cards
        requester_name = None
        requester_code = None
        details_summary = None

        if inst.module_type == "LEAVE":
            req_obj = service.db.get(LeaveRequest, inst.target_id)
            if req_obj:
                emp = service.db.get(Employee, req_obj.employee_id)
                if emp:
                    requester_name = f"{emp.first_name} {emp.last_name}"
                    requester_code = emp.employee_code
                details_summary = (
                    f"Leave Request ({req_obj.leave_type.name}) for {req_obj.total_days} "
                    f"day(s) from {req_obj.from_date} to {req_obj.to_date}. Reason: {req_obj.reason or 'No reason provided'}"
                )
        elif inst.module_type in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
            from app.models.time_entry import TimeEntry
            te_obj = service.db.get(TimeEntry, inst.target_id)
            if te_obj:
                emp = service.db.get(Employee, te_obj.employee_id)
                if emp:
                    requester_name = f"{emp.first_name} {emp.last_name}"
                    requester_code = emp.employee_code
                task_title = te_obj.task.title if te_obj.task else "Task"
                task_code = te_obj.task.task_code if te_obj.task else ""
                details_summary = (
                    f"Time Sheet ({te_obj.hours_spent} hrs) on {te_obj.date} "
                    f"for task {task_code} ({task_title}). Description: {te_obj.description or 'No description'}"
                )
        elif inst.module_type == "ATTENDANCE_CORRECTION":
            requester_name, requester_code, details_summary = _summarize_attendance_correction(
                service, inst.target_id
            )

        app_role = service.db.get(Role, inst.approver_role_id)
        assigned_emp = (
            service.db.get(Employee, inst.assigned_approver_id)
            if inst.assigned_approver_id
            else None
        )
        actioned_emp = (
            service.db.get(Employee, inst.actioned_by_id)
            if inst.actioned_by_id
            else None
        )
        resolved_emp = (
            service.db.get(Employee, inst.resolved_approver_id)
            if inst.resolved_approver_id
            else None
        )

        inst_resp = ApprovalInstanceResponse(
            id=inst.id,
            module_type=inst.module_type,
            target_id=inst.target_id,
            workflow_id=inst.workflow_id,
            workflow_version=inst.workflow_version,
            level=inst.level,
            approver_role_id=inst.approver_role_id,
            approver_role_name=app_role.name if app_role else None,
            assigned_approver_id=inst.assigned_approver_id,
            assigned_approver_name=(
                f"{assigned_emp.first_name} {assigned_emp.last_name}"
                if assigned_emp
                else None
            ),
            status=inst.status,
            actioned_by_id=inst.actioned_by_id,
            actioned_by_name=(
                f"{actioned_emp.first_name} {actioned_emp.last_name}"
                if actioned_emp
                else None
            ),
            actioned_at=inst.actioned_at,
            comments=inst.comments,
            resolved_by_scope=inst.resolved_by_scope,
            resolved_approver_id=inst.resolved_approver_id,
            resolved_approver_name=(
                f"{resolved_emp.first_name} {resolved_emp.last_name}"
                if resolved_emp
                else None
            ),
            resolution_time=inst.resolution_time,
            requester_name=requester_name,
            requester_code=requester_code,
            details_summary=details_summary,
        )
        result.append(inst_resp.model_dump())

    return APIResponse(
        success=True,
        message="Pending approvals retrieved successfully",
        data={"pending": result},
    )


@router.get("/history", response_model=APIResponse)
def get_approval_history(
    module_type: str | None = None,
    service: ApprovalService = Depends(_get_service),
):
    user_id = service.current_user_id
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User session not identified"
        )

    history_instances = service.get_approval_history(user_id, module_type=module_type)
    result = []

    for inst in history_instances:
        requester_name = None
        requester_code = None
        details_summary = None

        if inst.module_type == "LEAVE":
            req_obj = service.db.get(LeaveRequest, inst.target_id)
            if req_obj:
                emp = service.db.get(Employee, req_obj.employee_id)
                if emp:
                    requester_name = f"{emp.first_name} {emp.last_name}"
                    requester_code = emp.employee_code
                details_summary = (
                    f"Leave Request ({req_obj.leave_type.name}) for {req_obj.total_days} "
                    f"day(s) from {req_obj.from_date} to {req_obj.to_date}. Reason: {req_obj.reason or 'No reason provided'}"
                )
        elif inst.module_type in ("TIME SHEET", "TIMESHEET", "TIME_ENTRY"):
            from app.models.time_entry import TimeEntry
            te_obj = service.db.get(TimeEntry, inst.target_id)
            if te_obj:
                emp = service.db.get(Employee, te_obj.employee_id)
                if emp:
                    requester_name = f"{emp.first_name} {emp.last_name}"
                    requester_code = emp.employee_code
                task_title = te_obj.task.title if te_obj.task else "Task"
                task_code = te_obj.task.task_code if te_obj.task else ""
                details_summary = (
                    f"Time Sheet ({te_obj.hours_spent} hrs) on {te_obj.date} "
                    f"for task {task_code} ({task_title}). Description: {te_obj.description or 'No description'}"
                )
        elif inst.module_type == "ATTENDANCE_CORRECTION":
            requester_name, requester_code, details_summary = _summarize_attendance_correction(
                service, inst.target_id
            )

        app_role = service.db.get(Role, inst.approver_role_id)
        assigned_emp = (
            service.db.get(Employee, inst.assigned_approver_id)
            if inst.assigned_approver_id
            else None
        )
        actioned_emp = (
            service.db.get(Employee, inst.actioned_by_id)
            if inst.actioned_by_id
            else None
        )
        resolved_emp = (
            service.db.get(Employee, inst.resolved_approver_id)
            if inst.resolved_approver_id
            else None
        )

        inst_resp = ApprovalInstanceResponse(
            id=inst.id,
            module_type=inst.module_type,
            target_id=inst.target_id,
            workflow_id=inst.workflow_id,
            workflow_version=inst.workflow_version,
            level=inst.level,
            approver_role_id=inst.approver_role_id,
            approver_role_name=app_role.name if app_role else None,
            assigned_approver_id=inst.assigned_approver_id,
            assigned_approver_name=(
                f"{assigned_emp.first_name} {assigned_emp.last_name}"
                if assigned_emp
                else None
            ),
            status=inst.status,
            actioned_by_id=inst.actioned_by_id,
            actioned_by_name=(
                f"{actioned_emp.first_name} {actioned_emp.last_name}"
                if actioned_emp
                else None
            ),
            actioned_at=inst.actioned_at,
            comments=inst.comments,
            resolved_by_scope=inst.resolved_by_scope,
            resolved_approver_id=inst.resolved_approver_id,
            resolved_approver_name=(
                f"{resolved_emp.first_name} {resolved_emp.last_name}"
                if resolved_emp
                else None
            ),
            resolution_time=inst.resolution_time,
            requester_name=requester_name,
            requester_code=requester_code,
            details_summary=details_summary,
        )
        result.append(inst_resp.model_dump())

    return APIResponse(
        success=True,
        message="Approval history retrieved successfully",
        data={"history": result},
    )


@router.post("/instances/{id}/action", response_model=APIResponse)
def action_approval_step(
    id: uuid.UUID,
    data: ApprovalActionRequest,
    service: ApprovalService = Depends(_get_service),
):
    user_id = service.current_user_id
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User session not identified"
        )

    try:
        overall_status, rejection_reason = service.submit_approval_action(
            user_id, id, data.action, data.comments
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return APIResponse(
        success=True,
        message=f"Approval step {data.action} successfully",
        data={
            "overall_status": overall_status,
            "rejection_reason": rejection_reason,
        },
    )
