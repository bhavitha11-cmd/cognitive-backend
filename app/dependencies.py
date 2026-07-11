from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings, SUPER_ADMIN_CODES
from app.core.security import decode_token
from app.database.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> str:
    """Validate JWT access token and return the user ID string."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except (jwt.exceptions.InvalidTokenError, ValidationError):
        raise credentials_exception

    # Check if token has been revoked
    jti = payload.get("jti")
    if not jti:
        raise credentials_exception  # Reject tokens without JTI claim

    from app.models.revoked_token import RevokedToken
    revoked = db.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Security M1: offboarded/deactivated users must lose access immediately.
    # Resolve the employee and reject inactive accounts with 401.
    from app.models.employee import Employee
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise credentials_exception
    employee = db.scalar(select(Employee).where(Employee.id == user_uuid))
    if employee is None or not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


def require_permission(module_or_feature: str, action: str):
    """
    Return a FastAPI dependency that enforces RBAC using the Authorization Engine.

    Supports BOTH legacy module names (e.g. "Settings") and new feature keys
    (e.g. "roles", "employees"). The engine uses the new scope-based permission
    model via RolePermission.feature_id.

    Backward-compatible: if a legacy module name is passed, it is mapped to a
    feature_key automatically.
    """
    LEGACY_MODULE_MAP = {
        "HR": "employees",
        "Clients": "clients",
        "Finance": "settings",
        "Projects": "projects",
        "Parts": "parts",
        "Inventory": "settings",
        "Settings": "settings",
        "Reports": "reports",
        "Timesheets": "work_center",
        "Tasks": "tasks",
        "Attendance": "attendance",
        "Leave": "my_leaves",
        "Analytics": "advanced_dashboard",
        "Holiday": "calendar",
        "Calendar": "calendar",
        "CompanyEvent": "calendar",
        "Dashboard": "my_dashboard",
        "CalendarSettings": "calendar_configuration",
        "TaskTemplate": "task_title_library",
        "Productivity": "work_center",
    }

    # Normalize the module/feature to a feature key
    feature_key = LEGACY_MODULE_MAP.get(module_or_feature, module_or_feature)

    # Normalize legacy action names to new action names
    ACTION_MAP = {
        "view": "view",
        "create": "create",
        "edit": "update",
        "activate": "delete",
    }
    normalized_action = ACTION_MAP.get(action, action)

    def checker(
        current_user_id: str = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> str:
        from app.services.auth_engine_service import AuthorizationEngine

        try:
            user_uuid = UUID(current_user_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        engine = AuthorizationEngine(db)
        if engine.has_permission(user_uuid, feature_key, normalized_action):
            return current_user_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have '{action}' permission on '{module_or_feature}'",
        )

    return checker


def require_any_permission(*permission_specs: tuple[str, str]):
    """
    Return a FastAPI dependency that enforces RBAC.
    Pass multiple tuple specs, e.g. ("HR", "view"), ("Projects", "view").
    Allows access if ANY of the permissions are held.
    """
    LEGACY_MODULE_MAP = {
        "HR": "employees",
        "Clients": "clients",
        "Finance": "settings",
        "Projects": "projects",
        "Inventory": "settings",
        "Settings": "settings",
        "Reports": "reports",
        "Timesheets": "work_center",
        "Tasks": "tasks",
        "Attendance": "attendance",
        "Leave": "my_leaves",
        "Analytics": "advanced_dashboard",
        "Holiday": "calendar",
        "Calendar": "calendar",
        "CompanyEvent": "calendar",
        "Dashboard": "my_dashboard",
        "CalendarSettings": "calendar_configuration",
        "TaskTemplate": "task_title_library",
        "Productivity": "work_center",
    }
    ACTION_MAP = {
        "view": "view",
        "create": "create",
        "edit": "update",
        "activate": "delete",
    }

    def checker(
        current_user_id: str = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> str:
        from app.services.auth_engine_service import AuthorizationEngine

        try:
            user_uuid = UUID(current_user_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        engine = AuthorizationEngine(db)

        for module, action in permission_specs:
            feature_key = LEGACY_MODULE_MAP.get(module, module)
            normalized_action = ACTION_MAP.get(action, action)
            if engine.has_permission(user_uuid, feature_key, normalized_action):
                return current_user_id

        spec_str = ", ".join(f"'{m}:{a}'" for m, a in permission_specs)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Requires at least one of these permissions: {spec_str}",
        )

    return checker
