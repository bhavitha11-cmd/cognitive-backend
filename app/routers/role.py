import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.session import get_db
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.role_permission_audit import RolePermissionAudit
from app.models.feature import Feature
from app.schemas.role import (
    RoleCreate, RoleUpdate, RoleResponse,
    RolePermissionItem, RolePermissionList, RolePermissionResponse,
    FeaturePermissionBulkUpdate, ClonePermissionsRequest,
    RolePermissionScopeResponse,
)
from app.schemas.common import APIResponse
from app.services.role_service import RoleService
from app.dependencies import get_current_user, require_permission
from app.core.permission_scope import PermissionScope

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
               dependencies=[Depends(require_permission("Settings", "activate"))])
def delete_role(id: uuid.UUID, service: RoleService = Depends(_get_service)):
    try:
        service.delete(id)
    except ValueError as e:
        code = status.HTTP_404_NOT_FOUND if "not found" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))
    return APIResponse(success=True, message="Role deleted successfully")


# ── Legacy Permissions Endpoints (backward compat) ────────────────────────────

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


# ── New Scope-Based Permission Endpoints ──────────────────────────────────────

@router.get("/{id}/feature-permissions", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "view"))])
def get_role_feature_permissions(id: uuid.UUID, db: Session = Depends(get_db)):
    """Get scope-based permissions for a role, grouped by module > feature."""
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Load all features with their modules
    features = db.scalars(
        select(Feature)
        .where(Feature.is_active == True, Feature.permission_enabled == True)
        .order_by(Feature.display_order)
    ).all()

    # Load existing permissions for this role
    existing_perms = db.scalars(
        select(RolePermission)
        .where(RolePermission.role_id == id, RolePermission.feature_id.isnot(None))
    ).all()
    perm_map = {p.feature_id: p for p in existing_perms}

    results = []
    for feat in features:
        perm = perm_map.get(feat.id)
        results.append(RolePermissionScopeResponse(
            id=perm.id if perm else uuid.uuid4(),
            feature_id=feat.id,
            feature_key=feat.feature_key,
            feature_name=feat.feature_name,
            module_key=feat.module.module_key,
            module_name=feat.module.module_name,
            view_scope=perm.view_scope if perm else PermissionScope.NONE.value,
            create_scope=perm.create_scope if perm else PermissionScope.NONE.value,
            update_scope=perm.update_scope if perm else PermissionScope.NONE.value,
            delete_scope=perm.delete_scope if perm else PermissionScope.NONE.value,
        ))

    return APIResponse(
        success=True,
        message="Feature permissions retrieved",
        data={"permissions": [r.model_dump() for r in results]},
    )


@router.put("/{id}/feature-permissions", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "edit"))])
def set_role_feature_permissions(
    id: uuid.UUID,
    body: FeaturePermissionBulkUpdate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Bulk-update scope-based permissions for a role (the full matrix)."""
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Privilege escalation guard
    try:
        actor_uuid = uuid.UUID(current_user_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    try:
        RoleService(db).assert_can_edit_role_permissions(id, actor_uuid)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # Load all features
    features = db.scalars(
        select(Feature)
        .where(Feature.id.in_(feature_ids))
    ).all()
    feature_map = {f.id: f for f in features}

    missing = feature_ids - set(feature_map.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown feature IDs: {[str(m) for m in missing]}",
        )

    # Load existing permissions for this role
    existing_perms = db.scalars(
        select(RolePermission)
        .where(RolePermission.role_id == id, RolePermission.feature_id.isnot(None))
    ).all()
    perm_map = {p.feature_id: p for p in existing_perms}

    for perm_update in body.permissions:
        existing = perm_map.get(perm_update.feature_id)
        feature = feature_map[perm_update.feature_id]

        if existing:
            # Audit trail — record changes
            for action, new_scope in [
                ("view", perm_update.view_scope),
                ("create", perm_update.create_scope),
                ("update", perm_update.update_scope),
                ("delete", perm_update.delete_scope),
            ]:
                old_scope = getattr(existing, f"{action}_scope")
                if old_scope != new_scope:
                    db.add(RolePermissionAudit(
                        role_id=id,
                        feature_id=perm_update.feature_id,
                        action=action,
                        old_scope=old_scope,
                        new_scope=new_scope,
                        changed_by=actor_uuid,
                    ))

            existing.module_name = feature.feature_name
            existing.view_scope = perm_update.view_scope
            existing.create_scope = perm_update.create_scope
            existing.update_scope = perm_update.update_scope
            existing.delete_scope = perm_update.delete_scope
        else:
            # Insert new permission row
            db.add(RolePermission(
                role_id=id,
                feature_id=perm_update.feature_id,
                module_name=feature.feature_name,
                view_scope=perm_update.view_scope,
                create_scope=perm_update.create_scope,
                update_scope=perm_update.update_scope,
                delete_scope=perm_update.delete_scope,
            ))
            # Audit trail for new permission
            for action, new_scope in [
                ("view", perm_update.view_scope),
                ("create", perm_update.create_scope),
                ("update", perm_update.update_scope),
                ("delete", perm_update.delete_scope),
            ]:
                if new_scope != PermissionScope.NONE.value:
                    db.add(RolePermissionAudit(
                        role_id=id,
                        feature_id=perm_update.feature_id,
                        action=action,
                        old_scope=PermissionScope.NONE.value,
                        new_scope=new_scope,
                        changed_by=actor_uuid,
                    ))

    db.commit()
    return APIResponse(success=True, message="Feature permissions updated successfully")


@router.post("/{id}/clone-permissions", response_model=APIResponse,
             dependencies=[Depends(require_permission("Settings", "edit"))])
def clone_permissions(
    id: uuid.UUID,
    body: ClonePermissionsRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Copy all permissions from a source role to the target role."""
    target_role = db.get(Role, id)
    if not target_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target role not found")

    source_role = db.get(Role, body.source_role_id)
    if not source_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source role not found")

    # Delete existing feature permissions for target role
    existing_perms = db.scalars(
        select(RolePermission)
        .where(RolePermission.role_id == id, RolePermission.feature_id.isnot(None))
    ).all()
    for p in existing_perms:
        db.delete(p)

    # Copy permissions from source
    source_perms = db.scalars(
        select(RolePermission)
        .where(RolePermission.role_id == body.source_role_id, RolePermission.feature_id.isnot(None))
    ).all()

    for sp in source_perms:
        db.add(RolePermission(
            role_id=id,
            feature_id=sp.feature_id,
            module_name=sp.module_name,
            view_scope=sp.view_scope,
            create_scope=sp.create_scope,
            update_scope=sp.update_scope,
            delete_scope=sp.delete_scope,
        ))

    db.commit()
    return APIResponse(
        success=True,
        message=f"Permissions cloned from '{source_role.name}' to '{target_role.name}' successfully",
    )


# ── Legacy set permissions (kept for backward compatibility) ──────────────────

@router.put("/{id}/permissions", response_model=APIResponse,
            dependencies=[Depends(require_permission("Settings", "edit"))])
def set_role_permissions(
    id: uuid.UUID,
    body: RolePermissionList,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user),
):
    """Legacy endpoint — sets boolean-based module permissions."""
    role = db.get(Role, id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Privilege escalation guard
    try:
        actor_uuid = uuid.UUID(current_user_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    try:
        RoleService(db).assert_can_edit_role_permissions(id, actor_uuid)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # Build a lookup of existing permissions by module_name
    existing = {p.module_name: p for p in role.permissions if p.module_name}

    for perm in body.permissions:
        if perm.module_name in existing:
            entry = existing[perm.module_name]
            # Convert booleans to scope values on the new columns
            entry.view_scope = PermissionScope.ALL.value if perm.can_view else PermissionScope.NONE.value
            entry.create_scope = PermissionScope.ALL.value if perm.can_create else PermissionScope.NONE.value
            entry.update_scope = PermissionScope.ALL.value if perm.can_edit else PermissionScope.NONE.value
            entry.delete_scope = PermissionScope.ALL.value if perm.can_activate else PermissionScope.NONE.value
        else:
            # Look up a matching feature for new entries
            feature = db.scalar(
                select(Feature).where(Feature.feature_key == perm.module_name.lower())
            )
            db.add(RolePermission(
                role_id=id,
                module_name=perm.module_name,
                feature_id=feature.id if feature else None,
                view_scope=PermissionScope.ALL.value if perm.can_view else PermissionScope.NONE.value,
                create_scope=PermissionScope.ALL.value if perm.can_create else PermissionScope.NONE.value,
                update_scope=PermissionScope.ALL.value if perm.can_edit else PermissionScope.NONE.value,
                delete_scope=PermissionScope.ALL.value if perm.can_activate else PermissionScope.NONE.value,
            ))

    # Remove any existing permissions not in the incoming list
    incoming_modules = {p.module_name for p in body.permissions}
    for mod, entry in existing.items():
        if mod not in incoming_modules:
            db.delete(entry)

    db.commit()

    return APIResponse(success=True, message="Permissions updated successfully")
