from datetime import datetime, timezone, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from uuid import UUID

from app.database.session import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.config import SUPER_ADMIN_CODES
from app.dependencies import get_current_user
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.schemas.auth import Token, UserMeResponse, PermissionDetail, LoginRequest
from app.schemas.common import APIResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_employee_with_roles(db: Session, user_uuid: UUID) -> Employee | None:
    return db.scalars(
        select(Employee)
        .options(
            joinedload(Employee.employee_roles)
            .joinedload(EmployeeRole.role)
            .joinedload(Role.permissions)
        )
        .where(Employee.id == user_uuid)
    ).unique().first()


def _build_permissions(employee: Employee) -> tuple[list[str], list[str], dict]:
    roles, role_codes, permissions_map = [], [], {}
    for er in employee.employee_roles:
        if er.is_active and er.role:
            roles.append(er.role.name)
            role_codes.append(er.role.role_code)
            for p in er.role.permissions:
                mod = p.module_name
                if mod not in permissions_map:
                    permissions_map[mod] = {k: False for k in
                                            ("can_view", "can_create", "can_edit",
                                             "can_delete", "can_approve", "can_export")}
                for action in permissions_map[mod]:
                    permissions_map[mod][action] |= getattr(p, action)
    return roles, role_codes, permissions_map


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=APIResponse)
@limiter.limit("10/minute")
def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )

    query = (
        select(Employee)
        .options(joinedload(Employee.employee_roles).joinedload(EmployeeRole.role))
        .where(Employee.username == login_data.username)
    )
    employee = db.scalars(query).unique().first()

    if not employee:
        raise credentials_exception

    # Check if account is locked
    if employee.locked_until and employee.locked_until > datetime.now(timezone.utc):
        remaining = int((employee.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account locked due to too many failed attempts. Try again in {remaining} minute(s)."
        )

    if not verify_password(login_data.password, employee.password_hash):
        employee.failed_login_attempts = (employee.failed_login_attempts or 0) + 1
        if employee.failed_login_attempts >= 5:
            employee.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.add(employee)
        db.commit()
        raise credentials_exception

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    # Reset lockout counters on successful login
    employee.failed_login_attempts = 0
    employee.locked_until = None
    employee.last_login_at = datetime.now(timezone.utc)
    db.add(employee)

    access_token = create_access_token(subject=employee.id)
    refresh_token = create_refresh_token(subject=employee.id)

    db.commit()

    return APIResponse(
        success=True,
        message="Login successful",
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "employee": {
                "id": str(employee.id),
                "employee_code": employee.employee_code,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "email": employee.email,
                "username": employee.username,
            },
        },
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/token/refresh", response_model=APIResponse)
@limiter.limit("20/minute")
def token_refresh(request: Request, body: RefreshRequest, db: Session = Depends(get_db)):
    """Issue a new access token using a valid refresh token."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except jwt.exceptions.InvalidTokenError:
        raise credentials_exc

    # Reject if this refresh token has no JTI claim or has already been revoked
    jti = payload.get("jti")
    if not jti:
        raise credentials_exc  # Reject tokens without JTI claim

    from app.models.revoked_token import RevokedToken
    if db.scalar(select(RevokedToken).where(RevokedToken.jti == jti)):
        raise credentials_exc

    employee = db.get(Employee, UUID(user_id))
    if not employee or not employee.is_active:
        raise credentials_exc

    # Revoke the old refresh token (refresh token rotation)
    old_revoked = RevokedToken(
        jti=jti,
        revoked_at=datetime.now(timezone.utc),
        expires_at=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc),
    )
    db.add(old_revoked)
    db.flush()  # Persist revocation before issuing new tokens

    # Issue new access token and new refresh token (rotation)
    new_access = create_access_token(subject=employee.id)
    new_refresh = create_refresh_token(subject=employee.id)

    db.commit()

    return APIResponse(
        success=True,
        message="Token refreshed",
        data={"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"},
    )


def _revoke_token_if_valid(token_str: str, db, token_type: str | None = None) -> None:
    """Decode a JWT and add its JTI to the revoked_tokens table if not already there."""
    from app.models.revoked_token import RevokedToken
    from app.core.config import settings as _s
    try:
        payload = jwt.decode(token_str, _s.SECRET_KEY, algorithms=[_s.ALGORITHM])
        if token_type and payload.get("type") != token_type:
            return
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            already = db.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
            if not already:
                db.add(RevokedToken(jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)))
    except jwt.InvalidTokenError:
        pass  # Token already invalid/expired — nothing to revoke


@router.post("/logout", response_model=APIResponse)
@limiter.limit("20/minute")
def logout(
    request: Request,
    body: LogoutRequest = None,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Revoke access token
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    if access_token:
        _revoke_token_if_valid(access_token, db, token_type="access")

    # Revoke refresh token — makes logout truly complete even if attacker has the refresh token
    if body and body.refresh_token:
        _revoke_token_if_valid(body.refresh_token, db, token_type="refresh")

    db.commit()
    return APIResponse(success=True, message="Logged out successfully", data=None)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain at least one special character")
        return v


@router.post("/change-password", response_model=APIResponse)
@limiter.limit("5/minute")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    employee = db.get(Employee, UUID(current_user_id))
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(body.current_password, employee.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    employee.password_hash = get_password_hash(body.new_password)
    db.add(employee)
    db.commit()

    from app.services.audit_service import AuditService
    AuditService.log(db, "employee", employee.id, "CHANGE_PASSWORD",
                     performed_by=employee.id)

    return APIResponse(success=True, message="Password changed successfully")


@router.get("/me", response_model=APIResponse)
@limiter.limit("60/minute")
def get_me(
    request: Request,
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user_uuid = UUID(current_user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    employee = _load_employee_with_roles(db, user_uuid)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    roles, role_codes, permissions_map = _build_permissions(employee)

    # Resolve RBAC context for data access level
    from app.core.rbac import get_user_context
    user_ctx = get_user_context(db, current_user_id)

    # Super-admin gets full access on all modules
    if set(role_codes) & SUPER_ADMIN_CODES:
        for mod in ["HR", "Clients", "Finance", "Projects",
                    "Inventory", "Settings", "Reports", "Timesheets", "Tasks"]:
            permissions_map[mod] = {k: True for k in
                                    ("can_view", "can_create", "can_edit",
                                     "can_delete", "can_approve", "can_export")}

    permissions_list = [
        PermissionDetail(module_name=mod, **perms)
        for mod, perms in permissions_map.items()
    ]

    return APIResponse(
        success=True,
        message="User profile retrieved successfully",
        data=UserMeResponse(
            id=employee.id,
            employee_id=employee.id,
            employee_code=employee.employee_code,
            first_name=employee.first_name,
            last_name=employee.last_name,
            email=employee.email,
            username=employee.username,
            is_active=employee.is_active,
            roles=roles,
            role_codes=role_codes,
            data_access_level=user_ctx.data_access_level.value,
            permissions=permissions_list,
        ).model_dump(),
    )

