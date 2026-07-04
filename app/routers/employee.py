import uuid as uuid_lib
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import APIResponse
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    TransferReportsRequest,
    TransferTeamRequest,
    TransferDepartmentRequest,
)
from app.schemas.offboarding import OffboardExecuteRequest

from app.dependencies import get_current_user, require_permission, require_any_permission

router = APIRouter(
    prefix="/employees",
    tags=["Employees"],
    dependencies=[Depends(get_current_user)],
)


class BulkIdsRequest(BaseModel):
    ids: list[str]


# Phrases raised by the service that indicate a privilege-escalation attempt (C2).
# These are mapped to 403 rather than the generic 400.
_FORBIDDEN_MARKERS = (
    "super-admin",
    "assign roles to your own account",
)


def _error_status(e: Exception) -> int:
    msg = str(e).lower()
    if any(marker in msg for marker in _FORBIDDEN_MARKERS):
        return status.HTTP_403_FORBIDDEN
    if "not found" in msg:
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_400_BAD_REQUEST


def _get_service(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user)):
    from app.services.employee_service import EmployeeService
    from uuid import UUID
    try:
        uid = UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return EmployeeService(db, current_user_id=uid)


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_any_permission(("HR", "view"), ("Projects", "view"), ("Tasks", "view")))],
)
def list_employees(
    search: str | None = Query(None, description="Search by name or email"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(50, ge=1, le=200, description="Records to return"),
    department_id: str | None = Query(None, description="Filter by department UUID"),
    account_status: str | None = Query(None, description="Filter by account status"),
    service=Depends(_get_service),
):
    from uuid import UUID as _UUID
    dept_uuid = None
    if department_id:
        try:
            dept_uuid = _UUID(department_id)
        except ValueError:
            pass
    employees, total = service.get_all(
        search=search,
        skip=skip,
        limit=limit,
        department_id=dept_uuid,
        account_status=account_status,
    )
    return APIResponse(
        success=True,
        message="Employees retrieved successfully",
        data={
            "employees": [e.model_dump() for e in employees],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("HR", "create"))])
def create_employee(employee_in: EmployeeCreate, service=Depends(_get_service)):
    try:
        employee = service.create(employee_in)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(e), detail=str(e))
    return APIResponse(
        success=True,
        message="Employee created successfully",
        data={"employee": employee.model_dump()},
    )


@router.get("/lookup", response_model=APIResponse)
def lookup_employees(service=Depends(_get_service)):
    employees = service.get_lookup()
    return APIResponse(
        success=True,
        message="Employees lookup retrieved successfully",
        data={"employees": [e.model_dump() for e in employees]},
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_any_permission(("HR", "view"), ("Projects", "view"), ("Tasks", "view")))],
)
def get_employee(id: str, service=Depends(_get_service)):
    try:
        resolved = service._resolve_id(id)
        employee = service.get_by_id(resolved)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Employee retrieved successfully",
        data={"employee": employee.model_dump()},
    )


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("HR", "edit"))])
def update_employee(id: str, employee_in: EmployeeUpdate, service=Depends(_get_service)):
    try:
        resolved = service._resolve_id(id)
        employee = service.update(resolved, employee_in)
    except ValueError as e:
        raise HTTPException(status_code=_error_status(e), detail=str(e))
    return APIResponse(
        success=True,
        message="Employee updated successfully",
        data={"employee": employee.model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("HR", "activate"))])
def delete_employee(id: str, service=Depends(_get_service)):
    try:
        resolved = service._resolve_id(id)
        service.delete(resolved)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Employee deleted successfully", data=None)


# ---- Offboarding Workflow ----


@router.post("/{id}/offboard/check", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "edit"))])
def offboard_check(id: str, service=Depends(_get_service)):
    try:
        resolved = service._resolve_id(id)
        check = service.offboard_check(resolved)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Offboarding check complete",
        data=check.model_dump(),
    )


@router.post("/{id}/offboard/confirm", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "activate"))])
def offboard_confirm(
    id: str,
    final_status: str = Query("RESIGNED", description="Final status", enum=["RESIGNED", "TERMINATED"]),
    service=Depends(_get_service),
):
    try:
        resolved = service._resolve_id(id)
        employee = service.offboard_confirm(resolved, final_status)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Employee offboarded with status '{final_status}'",
        data={"employee": employee.model_dump()},
    )


@router.post("/{id}/transfer-reports", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "edit"))])
def transfer_reports(
    id: str,
    body: TransferReportsRequest,
    service=Depends(_get_service),
):
    try:
        resolved = service._resolve_id(id)
        results = service.transfer_reports(resolved, body.new_manager_id, body.employee_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"{len(results)} direct report(s) transferred",
        data={"transferred": [e.model_dump() for e in results]},
    )


@router.post("/{id}/transfer-teams", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "edit"))])
def transfer_teams(
    id: str,
    body: TransferTeamRequest,
    service=Depends(_get_service),
):
    try:
        resolved = service._resolve_id(id)
        service.transfer_teams(resolved, body.new_lead_id, body.team_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"{len(body.team_ids)} team(s) leadership transferred",
    )


@router.post("/{id}/transfer-departments", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "edit"))])
def transfer_departments(
    id: str,
    body: TransferDepartmentRequest,
    service=Depends(_get_service),
):
    try:
        resolved = service._resolve_id(id)
        service.transfer_departments(resolved, body.new_head_id, body.department_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message=f"{len(body.department_ids)} department(s) head transferred",
    )


# ---- Enterprise Ownership Transfer ----


@router.get(
    "/{id}/offboard/impact",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "edit"))],
)
def offboard_impact(id: str, service=Depends(_get_service)):
    """Full impact analysis before executing offboarding."""
    from app.services.ownership_transfer_service import OwnershipTransferService
    transfer_svc = OwnershipTransferService(service.db, current_user_id=service.current_user_id)
    try:
        resolved = service._resolve_id(id)
        impact = transfer_svc.compute_impact(resolved)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Impact analysis complete",
        data=impact.model_dump(),
    )


@router.post(
    "/{id}/offboard/execute",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "activate"))],
)
def offboard_execute(id: str, body: OffboardExecuteRequest, service=Depends(_get_service)):
    """Single atomic offboarding: transfers all ownership then sets employee inactive."""
    from app.services.ownership_transfer_service import OwnershipTransferService
    from sqlalchemy.exc import SQLAlchemyError
    transfer_svc = OwnershipTransferService(service.db, current_user_id=service.current_user_id)
    try:
        resolved = service._resolve_id(id)
        result = transfer_svc.execute_offboard(resolved, body)
        service.db.commit()
    except ValueError as e:
        service.db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SQLAlchemyError as e:
        service.db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Offboard transaction failed; all changes rolled back.")
    return APIResponse(
        success=True,
        message=f"Employee offboarded successfully with status '{result.final_status}'",
        data=result.model_dump(),
    )


# ---- History Endpoints ----


@router.get(
    "/{id}/role-history",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "view"))],
)
def get_role_history(id: str, service=Depends(_get_service)):
    resolved = service._resolve_id(id)
    history = service.get_role_history(resolved)
    return APIResponse(
        success=True,
        message="Role history retrieved",
        data={"history": history},
    )


@router.get(
    "/{id}/reporting-history",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "view"))],
)
def get_reporting_history(id: str, service=Depends(_get_service)):
    resolved = service._resolve_id(id)
    history = service.get_reporting_history(resolved)
    return APIResponse(
        success=True,
        message="Reporting history retrieved",
        data={"history": history},
    )


@router.get(
    "/{id}/direct-reports",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("HR", "view"))],
)
def get_direct_reports(id: str, service=Depends(_get_service)):
    from app.services.employee_service import EmployeeService
    resolved = service._resolve_id(id)
    check = service.offboard_check(resolved)
    direct_report_ids = []
    for b in check.blockers:
        if b.type == "direct_reports":
            direct_report_ids = [item["id"] for item in b.items]
    return APIResponse(
        success=True,
        message="Direct reports retrieved",
        data={"direct_report_ids": direct_report_ids},
    )


# ---- Deprecated endpoints ----


@router.patch("/{id}/deactivate", response_model=APIResponse,
              dependencies=[Depends(require_permission("HR", "activate"))])
def deactivate_employee(id: str, service=Depends(_get_service)):
    try:
        resolved = service._resolve_id(id)
        employee = service.deactivate(resolved)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Employee deactivated successfully",
        data={"employee": employee.model_dump()},
    )


@router.post("/bulk-deactivate", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "activate"))])
def bulk_deactivate_employees(body: BulkIdsRequest, service=Depends(_get_service)):
    try:
        service.bulk_deactivate(body.ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(success=True, message="Deprecated endpoint", data=None)


@router.post("/bulk-delete", response_model=APIResponse,
             dependencies=[Depends(require_permission("HR", "activate"))])
def bulk_delete_employees(body: BulkIdsRequest, service=Depends(_get_service)):
    try:
        service.bulk_delete(body.ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(success=True, message="Deprecated endpoint", data=None)
