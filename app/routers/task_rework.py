import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.common import APIResponse
from app.schemas.task_rework import TaskReworkClose, TaskReworkCreate
from app.services.rework_service import ReworkService

router = APIRouter(
    prefix="/task-rework",
    tags=["Task Rework"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> ReworkService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity"
        )
    return ReworkService(db, current_user_id=uid)


# ── Open a rework cycle ───────────────────────────────────────────────────────


@router.post(
    "/open",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def open_rework(
    data: TaskReworkCreate,
    service: ReworkService = Depends(_get_service),
):
    try:
        rework = service.open_rework(
            task_id=data.task_id,
            reason=data.reason,
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
        message="Rework cycle opened",
        data={"rework": rework.model_dump()},
    )


# ── Close a rework cycle ──────────────────────────────────────────────────────


@router.post(
    "/{rework_id}/close",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "edit"))],
)
def close_rework(
    rework_id: uuid.UUID,
    data: TaskReworkClose,
    service: ReworkService = Depends(_get_service),
):
    try:
        rework = service.close_rework(
            rework_id=rework_id,
            hours_spent=data.hours_spent,
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
        message="Rework cycle closed",
        data={"rework": rework.model_dump()},
    )


# ── Get rework history for a task ─────────────────────────────────────────────


@router.get("/by-task/{task_id}", response_model=APIResponse)
def get_rework_history(
    task_id: uuid.UUID,
    service: ReworkService = Depends(_get_service),
):
    history = service.get_task_rework_history(task_id)
    return APIResponse(
        success=True,
        message="Rework history retrieved",
        data={
            "rework_history": [h.model_dump() for h in history],
        },
    )


# ── Get open rework cycles ────────────────────────────────────────────────────


@router.get(
    "/open",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Tasks", "view"))],
)
def get_open_rework_cycles(
    service: ReworkService = Depends(_get_service),
):
    cycles = service.get_open_rework_cycles()
    return APIResponse(
        success=True,
        message="Open rework cycles retrieved",
        data={
            "open_cycles": [c.model_dump() for c in cycles],
        },
    )
