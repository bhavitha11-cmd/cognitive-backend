from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.security import decode_token
from app.database.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

SUPER_ADMIN_CODES = {"ADMIN", "CEO", "CHIEF_EXECUTIVE_OFFICER", "ADMINISTRATOR"}


async def get_current_user(
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
    except (JWTError, ValidationError):
        raise credentials_exception

    # Check if token has been revoked
    jti = payload.get("jti")
    if jti:
        from app.models.revoked_token import RevokedToken
        from sqlalchemy import select
        revoked = db.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
        if revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user_id


def require_permission(module: str, action: str):
    """
    Return a FastAPI dependency that enforces RBAC.
    action must be one of: view, create, edit, delete, approve, export
    """
    async def checker(
        current_user_id: str = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> str:
        from app.models.employee import Employee
        from app.models.employee_role import EmployeeRole
        from app.models.role import Role

        try:
            user_uuid = UUID(current_user_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        employee = db.scalars(
            __import__("sqlalchemy", fromlist=["select"]).select(Employee)
            .options(
                joinedload(Employee.employee_roles)
                .joinedload(EmployeeRole.role)
                .joinedload(Role.permissions)
            )
            .where(Employee.id == user_uuid)
        ).unique().first()

        if not employee or not employee.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Super-admin bypass
        for er in employee.employee_roles:
            if er.is_active and er.role:
                if er.role.role_code in SUPER_ADMIN_CODES or getattr(er.role, "is_super_admin", False):
                    return current_user_id

        # Module-level permission check
        action_field = f"can_{action}"
        for er in employee.employee_roles:
            if not er.is_active or not er.role:
                continue
            for perm in er.role.permissions:
                if perm.module_name == module and getattr(perm, action_field, False):
                    return current_user_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have '{action}' permission on module '{module}'",
        )

    return checker
