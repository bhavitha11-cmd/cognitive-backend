import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.work_session import (
    WorkSessionCreate,
    WorkSessionPause,
)
from app.services.work_session_service import WorkSessionService

router = APIRouter(
    prefix="/work-sessions",
    tags=["Work Sessions"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> WorkSessionService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity"
        )
    return WorkSessionService(db, current_user_id=uid)


# ── Start a work session ──────────────────────────────────────────────────────


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def start_session(
    data: WorkSessionCreate,
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.start_session(
            task_id=data.task_id,
            project_id=data.project_id,
            session_type=data.session_type,
        )
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Work session started",
        data={"work_session": session.model_dump()},
    )


# ── Pause a session ───────────────────────────────────────────────────────────


@router.post("/{session_id}/pause", response_model=APIResponse)
def pause_session(
    session_id: uuid.UUID,
    body: WorkSessionPause | None = None,
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.pause_session(
            session_id, reason=body.reason if body else None
        )
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Work session paused",
        data={"work_session": session.model_dump()},
    )


# ── Resume a session ──────────────────────────────────────────────────────────


@router.post("/{session_id}/resume", response_model=APIResponse)
def resume_session(
    session_id: uuid.UUID,
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.resume_session(session_id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Work session resumed",
        data={"work_session": session.model_dump()},
    )


# ── Complete a session ────────────────────────────────────────────────────────

from pydantic import BaseModel

class CompleteSessionBody(BaseModel):
    remarks: str | None = None
    mark_task_complete: bool = False

@router.post("/{session_id}/complete", response_model=APIResponse)
def complete_session(
    session_id: uuid.UUID,
    body: CompleteSessionBody = CompleteSessionBody(),
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.complete_session(
            session_id,
            remarks=body.remarks,
            mark_task_complete=body.mark_task_complete,
        )
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Work session completed",
        data={"work_session": session.model_dump()},
    )


# ── Cancel a session ──────────────────────────────────────────────────────────


@router.post("/{session_id}/cancel", response_model=APIResponse)
def cancel_session(
    session_id: uuid.UUID,
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.cancel_session(session_id)
    except ValueError as e:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(e).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Work session cancelled",
        data={"work_session": session.model_dump()},
    )


# ── Get active session ────────────────────────────────────────────────────────


@router.get("/active", response_model=APIResponse)
def get_active_session(
    service: WorkSessionService = Depends(_get_service),
):
    try:
        session = service.get_active_session()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Active session retrieved",
        data={
            "active_session": session.model_dump() if session else None
        },
    )


# ── Get my sessions ───────────────────────────────────────────────────────────


@router.get("/my", response_model=APIResponse)
def get_my_sessions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: WorkSessionService = Depends(_get_service),
):
    try:
        sessions, total = service.get_my_sessions(
            date_from=date_from,
            date_to=date_to,
            status=status,
            skip=skip,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Sessions retrieved",
        data={
            "work_sessions": [s.model_dump() for s in sessions],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


# ── Get daily summary ─────────────────────────────────────────────────────────


@router.get("/daily-summary", response_model=APIResponse)
def get_daily_summary(
    employee_id: uuid.UUID | None = Query(default=None),
    summary_date: date | None = Query(default=None),
    service: WorkSessionService = Depends(_get_service),
):
    # IDOR guard: non-management users can only view their own daily summary
    target_id = employee_id or service.current_user_id
    if str(target_id) != str(service.current_user_id):
        # Require explicit management permission to view another employee's summary
        from app.core.rbac import get_user_context, DataAccessLevel
        from app.database.session import get_db as _get_db
        # Access check via service's db session
        from app.core.rbac import DataAccessLevel as _DAL
        user_ctx = getattr(service, "_user_ctx", None)
        # Fallback: use require_permission dependency at call time is not available here,
        # so we resolve context inline from the service's db using current_user_id
        from app.core.rbac import get_user_context as _get_ctx
        ctx = _get_ctx(service.db, str(service.current_user_id))
        if ctx.data_access_level == _DAL.SELF:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own daily summary",
            )
    try:
        summary = service.get_daily_summary(
            employee_id=target_id,
            summary_date=summary_date,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Daily summary retrieved",
        data={"summary": summary.model_dump()},
    )


# ── Get sessions for a task ───────────────────────────────────────────────────


@router.get("/by-task/{task_id}", response_model=APIResponse)
def get_task_sessions(
    task_id: uuid.UUID,
    service: WorkSessionService = Depends(_get_service),
):
    sessions = service.get_task_sessions(task_id)
    return APIResponse(
        success=True,
        message="Task sessions retrieved",
        data={
            "work_sessions": [s.model_dump() for s in sessions],
        },
    )


# ── List all sessions (admin) ─────────────────────────────────────────────────


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def list_all_sessions(
    employee_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: WorkSessionService = Depends(_get_service),
):
    sessions, total = service.get_all_sessions(
        employee_id=employee_id,
        task_id=task_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        skip=skip,
        limit=limit,
    )
    return APIResponse(
        success=True,
        message="Sessions retrieved",
        data={
            "work_sessions": [s.model_dump() for s in sessions],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


# ── Get running sessions (crash recovery, Rule 11) ────────────────────────────


@router.get("/running", response_model=APIResponse)
def get_running_sessions(
    service: WorkSessionService = Depends(_get_service),
):
    sessions = service.get_running_sessions()
    return APIResponse(
        success=True,
        message="Running sessions retrieved",
        data={
            "running_sessions": [s.model_dump() for s in sessions],
        },
    )
