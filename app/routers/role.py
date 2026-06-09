import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, RolePermissionItem, RolePermissionResponse
from app.schemas.common import APIResponse
from app.services.role_service import RoleService

from app.dependencies import get_current_user

router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get("", response_model=APIResponse)
def get_roles(service: RoleService = Depends(_get_service)):
    roles = service.get_all()
    return APIResponse(
        success=True,
        message="Roles retrieved successfully",
        data={"roles": [RoleResponse.model_validate(r).model_dump() for r in roles]},
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
def create_role(role_in: RoleCreate, service: RoleService = Depends(_get_service)):
    try:
        role = service.create(role_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Role created successfully",
        data={"role": RoleResponse.model_validate(role).model_dump()},
    )


@router.put("/{id}", response_model=APIResponse)
def update_role(id: uuid.UUID, role_in: RoleUpdate, service: RoleService = Depends(_get_service)):
    try:
        role = service.update(id, role_in)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(
        success=True,
        message="Role updated successfully",
        data={"role": RoleResponse.model_validate(role).model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse)
def delete_role(id: uuid.UUID, service: RoleService = Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(success=True, message="Role deleted successfully", data=None)


# ---- Permissions ----


@router.get("/{id}/permissions", response_model=APIResponse)
def get_role_permissions(id: uuid.UUID, db: Session = Depends(get_db)):
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    permissions = role.permissions
    return APIResponse(
        success=True,
        message="Permissions retrieved",
        data={"permissions": [
            RolePermissionResponse(
                id=p.id,
                role_id=p.role_id,
                module_name=p.module_name,
                can_view=p.can_view,
                can_create=p.can_create,
                can_edit=p.can_edit,
                can_delete=p.can_delete,
                can_approve=p.can_approve,
                can_export=p.can_export,
            ).model_dump()
            for p in permissions
        ]},
    )


@router.put("/{id}/permissions", response_model=APIResponse)
def set_role_permissions(
    id: uuid.UUID,
    permissions: list[RolePermissionItem],
    db: Session = Depends(get_db),
):
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Remove existing
    for p in role.permissions:
        db.delete(p)

    # Add new
    for perm in permissions:
        rp = RolePermission(
            role_id=id,
            module_name=perm.module_name,
            can_view=perm.can_view,
            can_create=perm.can_create,
            can_edit=perm.can_edit,
            can_delete=perm.can_delete,
            can_approve=perm.can_approve,
            can_export=perm.can_export,
        )
        db.add(rp)

    db.commit()
    return APIResponse(success=True, message="Permissions updated successfully")
