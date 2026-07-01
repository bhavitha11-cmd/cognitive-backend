import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, RolePermissionItem, RolePermissionList, RolePermissionResponse
from app.schemas.common import APIResponse
from app.services.role_service import RoleService
from app.dependencies import get_current_user, require_permission

router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
    dependencies=[Depends(get_current_user)],
)


def _get_service(db: Session = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get("", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "view"))])
def get_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    service: RoleService = Depends(_get_service),
):
    roles = service.get_all()
    total = len(roles)
    paginated = roles[skip: skip + limit]
    return APIResponse(
        success=True,
        message="Roles retrieved successfully",
        data={
            "roles": [RoleResponse.model_validate(r).model_dump() for r in paginated],
            "total": total,
            "skip": skip,
            "limit": limit,
        },
    )


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_permission("Settings", "create"))])
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


@router.put("/{id}", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "edit"))])
def update_role(id: uuid.UUID, role_in: RoleUpdate, service: RoleService = Depends(_get_service)):
    try:
        role = service.update(id, role_in)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(
        success=True,
        message="Role updated successfully",
        data={"role": RoleResponse.model_validate(role).model_dump()},
    )


@router.delete("/{id}", response_model=APIResponse,
               dependencies=[Depends(require_permission("Settings", "delete"))])
def delete_role(id: uuid.UUID, service: RoleService = Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Role deleted successfully")


# ── Permissions ───────────────────────────────────────────────────────────────

@router.get("/{id}/permissions", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "view"))])
def get_role_permissions(id: uuid.UUID, db: Session = Depends(get_db)):
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return APIResponse(
        success=True,
        message="Permissions retrieved",
        data={"permissions": [
            RolePermissionResponse.model_validate(p).model_dump()
            for p in role.permissions
        ]},
    )


@router.put("/{id}/permissions", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "edit"))])
def set_role_permissions(
    id: uuid.UUID,
    body: RolePermissionList,
    db: Session = Depends(get_db),
):
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    VALID_MODULES = {
        "HR", "Projects", "Tasks", "Clients", "Timesheets", "Leave",
        "Attendance", "Analytics", "Settings", "Calendar", "Dashboard",
        "Holiday", "TaskTemplate", "CalendarSettings", "Productivity"
    }
    for perm in body.permissions:
        if perm.module_name not in VALID_MODULES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown module: {perm.module_name}. Valid modules: {sorted(VALID_MODULES)}"
            )

    # Build a lookup of existing permissions by module_name
    existing = {p.module_name: p for p in role.permissions}

    for perm in body.permissions:
        if perm.module_name in existing:
            entry = existing[perm.module_name]
            entry.can_view = perm.can_view
            entry.can_create = perm.can_create
            entry.can_edit = perm.can_edit
            entry.can_delete = perm.can_delete
            entry.can_approve = perm.can_approve
            entry.can_export = perm.can_export
        else:
            db.add(RolePermission(
                role_id=id,
                module_name=perm.module_name,
                can_view=perm.can_view,
                can_create=perm.can_create,
                can_edit=perm.can_edit,
                can_delete=perm.can_delete,
                can_approve=perm.can_approve,
                can_export=perm.can_export,
            ))

    # Remove any existing permissions not in the incoming list
    incoming_modules = {p.module_name for p in body.permissions}
    for mod, entry in existing.items():
        if mod not in incoming_modules:
            db.delete(entry)

    db.commit()

    return APIResponse(success=True, message="Permissions updated successfully")
