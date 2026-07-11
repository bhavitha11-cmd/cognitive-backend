import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.leave import (
    LeaveApprovalRequest,
    LeaveRequestCreate,
    LeaveRequestUpdate,
    LeaveTypeCreate,
    LeaveTypeUpdate,
)
from app.services.leave_service import LeaveService

router = APIRouter(
    prefix="/leaves",
    tags=["Leave Management"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> LeaveService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return LeaveService(db, current_user_id=uid)


# ── Leave Types ────────────────────────────────────────────────────────────────

@router.get("/types", response_model=APIResponse)
def list_leave_types(
    include_inactive: bool = Query(False),
    service: LeaveService = Depends(_get_service),
):
    leave_types = service.get_all_leave_types(include_inactive=include_inactive)
    return APIResponse(
        success=True,
        message="Leave types retrieved successfully",
        data={
            "leave_types": [lt.model_dump() for lt in leave_types],
            "total": len(leave_types),
        },
    )


@router.post(
    "/types",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Leave", "create"))],
)
def create_leave_type(
    data: LeaveTypeCreate,
    service: LeaveService = Depends(_get_service),
):
    try:
        lt = service.create_leave_type(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave type created successfully",
        data={"leave_type": lt.model_dump()},
    )


@router.put(
    "/types/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "edit"))],
)
def update_leave_type(
    id: uuid.UUID,
    data: LeaveTypeUpdate,
    service: LeaveService = Depends(_get_service),
):
    try:
        lt = service.update_leave_type(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave type updated successfully",
        data={"leave_type": lt.model_dump()},
    )


@router.delete(
    "/types/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "activate"))],
)
def delete_leave_type(
    id: uuid.UUID,
    service: LeaveService = Depends(_get_service),
):
    try:
        service.delete_leave_type(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Leave type deactivated successfully")


# ── Leave Balances ─────────────────────────────────────────────────────────────

@router.get("/balances", response_model=APIResponse)
def get_my_balances(
    year: int | None = Query(None),
    service: LeaveService = Depends(_get_service),
):
    if not service.current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not identify current user"
        )
    balances = service.get_balance(service.current_user_id, year=year)
    return APIResponse(
        success=True,
        message="Leave balances retrieved successfully",
        data={
            "balances": [b.model_dump() for b in balances],
            "total": len(balances),
            "year": year or datetime.now(timezone.utc).year,
        },
    )


@router.get(
    "/balances/{employee_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "view"))],
)
def get_employee_balances(
    employee_id: uuid.UUID,
    year: int | None = Query(None),
    service: LeaveService = Depends(_get_service),
):
    balances = service.get_balance(employee_id, year=year)
    return APIResponse(
        success=True,
        message="Leave balances retrieved successfully",
        data={
            "balances": [b.model_dump() for b in balances],
            "total": len(balances),
            "year": year or datetime.now(timezone.utc).year,
        },
    )


@router.post(
    "/balances/initialize/{employee_id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "edit"))],
)
def initialize_employee_balances(
    employee_id: uuid.UUID,
    year: int | None = Query(None),
    service: LeaveService = Depends(_get_service),
):
    try:
        balances = service.initialize_balances(employee_id, year=year)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave balances initialized successfully",
        data={
            "balances": [b.model_dump() for b in balances],
            "total": len(balances),
        },
    )


# ── Leave Requests ─────────────────────────────────────────────────────────────

@router.get("/requests/my", response_model=APIResponse)
def get_my_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    year: int | None = Query(None),
    service: LeaveService = Depends(_get_service),
):
    requests, total = service.get_my_requests(
        skip=skip, limit=limit, status=status, year=year
    )
    return APIResponse(
        success=True,
        message="Leave requests retrieved successfully",
        data={
            "requests": [r.model_dump() for r in requests],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get(
    "/requests",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "view"))],
)
def list_all_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    employee_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    year: int | None = Query(None),
    service: LeaveService = Depends(_get_service),
):
    requests, total = service.get_all_requests(
        skip=skip,
        limit=limit,
        employee_id=employee_id,
        status=status,
        year=year,
    )
    return APIResponse(
        success=True,
        message="Leave requests retrieved successfully",
        data={
            "requests": [r.model_dump() for r in requests],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post(
    "/requests",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_leave(
    data: LeaveRequestCreate,
    service: LeaveService = Depends(_get_service),
):
    try:
        req = service.apply_leave(data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave request submitted successfully",
        data={"request": req.model_dump()},
    )


@router.get("/requests/{id}", response_model=APIResponse)
def get_leave_request(
    id: uuid.UUID,
    service: LeaveService = Depends(_get_service),
):
    try:
        req = service.get_request(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Only the owner can view a specific request; managers use the list endpoint
    if req.employee_id != service.current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own leave requests",
        )

    return APIResponse(
        success=True,
        message="Leave request retrieved successfully",
        data={"request": req.model_dump()},
    )


@router.put("/requests/{id}", response_model=APIResponse)
def update_leave_request(
    id: uuid.UUID,
    data: LeaveRequestUpdate,
    service: LeaveService = Depends(_get_service),
):
    # Ownership check: only the owner may update their own leave request
    try:
        existing = service.get_request(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if existing.employee_id != service.current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own leave requests",
        )
    try:
        req = service.update_leave_request(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave request updated successfully",
        data={"request": req.model_dump()},
    )


@router.post("/requests/{id}/cancel", response_model=APIResponse)
def cancel_leave_request(
    id: uuid.UUID,
    service: LeaveService = Depends(_get_service),
):
    # Ownership check: only the owner may cancel their own leave request
    try:
        existing = service.get_request(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if existing.employee_id != service.current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own leave requests",
        )
    try:
        req = service.cancel_leave(id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Leave request cancelled successfully",
        data={"request": req.model_dump()},
    )


@router.post(
    "/requests/{id}/approve",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Leave", "edit"))],
)
def approve_or_reject_leave(
    id: uuid.UUID,
    data: LeaveApprovalRequest,
    service: LeaveService = Depends(_get_service),
):
    try:
        req = service.approve_or_reject(id, data)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message=f"Leave request {data.action.upper()} successfully",
        data={"request": req.model_dump()},
    )


@router.post("/upload", response_model=APIResponse)
def upload_leave_document(
    file: UploadFile = File(...),
):
    import os
    import shutil

    # Ensure uploads directory exists
    uploads_dir = os.path.join(os.getcwd(), "uploads", "leave_documents")
    os.makedirs(uploads_dir, exist_ok=True)

    file_id = uuid.uuid4()
    extension = os.path.splitext(file.filename)[1]
    filename = f"{file_id}{extension}"
    filepath = os.path.join(uploads_dir, filename)

    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    # Return download url
    return APIResponse(
        success=True,
        message="Document uploaded successfully",
        data={"url": f"/api/v1/leaves/document/{filename}"}
    )


@router.get("/document/{filename}")
def get_leave_document(filename: str):
    import os
    uploads_dir = os.path.join(os.getcwd(), "uploads", "leave_documents")
    filepath = os.path.join(uploads_dir, filename)

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    return FileResponse(filepath)
