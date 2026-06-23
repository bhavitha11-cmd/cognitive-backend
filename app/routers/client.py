import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/clients",
    tags=["Clients"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    from app.services.client_service import ClientService
    from uuid import UUID

    try:
        uid = UUID(current_user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    return ClientService(db, current_user_id=uid)


@router.get("", response_model=APIResponse)
def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    service=Depends(_get_service),
):
    clients, total = service.get_all(skip=skip, limit=limit, search=search, is_active=is_active)
    return APIResponse(
        success=True,
        message="Clients retrieved successfully",
        data={
            "clients": [c.model_dump() for c in clients],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("Clients", "create"))],
)
def create_client(client_in: ClientCreate, service=Depends(_get_service)):
    try:
        client = service.create(client_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Client created successfully",
        data={"client": client.model_dump()},
    )


@router.get("/{id}", response_model=APIResponse)
def get_client(id: uuid.UUID, service=Depends(_get_service)):
    try:
        client = service.get_by_id(id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return APIResponse(
        success=True,
        message="Client retrieved successfully",
        data={"client": client.model_dump()},
    )


@router.put(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Clients", "edit"))],
)
def update_client(id: uuid.UUID, client_in: ClientUpdate, service=Depends(_get_service)):
    try:
        client = service.update(id, client_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Client updated successfully",
        data={"client": client.model_dump()},
    )


@router.delete(
    "/{id}",
    response_model=APIResponse,
    dependencies=[Depends(require_permission("Clients", "delete"))],
)
def delete_client(id: uuid.UUID, service=Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Client deleted successfully")
