import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user
from app.schemas.common import APIResponse
from app.schemas.employee_break import BreakEndRequest, BreakStartRequest
from app.services.break_service import BreakService

router = APIRouter(
    prefix="/breaks",
    tags=["Breaks"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
) -> BreakService:
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity"
        )
    return BreakService(db, current_user_id=uid)


# ── Start a break ─────────────────────────────────────────────────────────────


@router.post("/start", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def start_break(
    body: BreakStartRequest | None = None,
    service: BreakService = Depends(_get_service),
):
    try:
        break_record = service.start_break(
            remarks=body.remarks if body else None
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
        message="Break started",
        data={"break_record": break_record.model_dump()},
    )


# ── End a break ───────────────────────────────────────────────────────────────


@router.post("/end", response_model=APIResponse)
def end_break(
    body: BreakEndRequest | None = None,
    service: BreakService = Depends(_get_service),
):
    try:
        break_record = service.end_break(
            remarks=body.remarks if body else None
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
        message="Break ended",
        data={"break_record": break_record.model_dump()},
    )


# ── Get active break ──────────────────────────────────────────────────────────


@router.get("/active", response_model=APIResponse)
def get_active_break(
    service: BreakService = Depends(_get_service),
):
    break_record = service.get_active_break()
    return APIResponse(
        success=True,
        message="Active break retrieved",
        data={"active_break": break_record.model_dump() if break_record else None},
    )


# ── Get my breaks ─────────────────────────────────────────────────────────────


@router.get("/my", response_model=APIResponse)
def get_my_breaks(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: BreakService = Depends(_get_service),
):
    try:
        breaks, total = service.get_my_breaks(
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return APIResponse(
        success=True,
        message="Breaks retrieved",
        data={
            "break_records": [b.model_dump() for b in breaks],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )
