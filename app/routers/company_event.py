from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.calendar import CompanyEventCreate, CompanyEventResponse, CompanyEventUpdate
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/company-events",
    tags=["Company Events"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.company_event_service import CompanyEventService
    try:
        uid = uuid.UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return CompanyEventService(db, current_user_id=uid)


@router.get(
    "",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("CompanyEvent", "view"))],
)
def list_company_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    is_active: bool | None = Query(None),
    service=Depends(_get_service),
):
    items, total = service.get_all(
        skip=skip, limit=limit, from_date=from_date, to_date=to_date, is_active=is_active
    )
    return APIResponse(
        success=True,
        message="Company events retrieved",
        data={
            "events": [e.model_dump(mode="json") for e in items],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.get(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("CompanyEvent", "view"))],
)
def get_company_event(id: uuid.UUID, service=Depends(_get_service)):
    try:
        event = service.get_by_id(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(
        success=True,
        message="Company event retrieved",
        data={"event": event.model_dump(mode="json")},
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CompanyEvent", "create"))],
)
def create_company_event(data: CompanyEventCreate, service=Depends(_get_service)):
    event = service.create(data)
    return APIResponse(
        success=True,
        message="Company event created",
        data={"event": event.model_dump(mode="json")},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("CompanyEvent", "edit"))],
)
def update_company_event(id: uuid.UUID, data: CompanyEventUpdate, service=Depends(_get_service)):
    try:
        event = service.update(id, data)
    except ValueError as e:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))
    return APIResponse(
        success=True,
        message="Company event updated",
        data={"event": event.model_dump(mode="json")},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("CompanyEvent", "delete"))],
)
def delete_company_event(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return APIResponse(success=True, message="Company event deactivated")
