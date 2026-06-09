from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from uuid import UUID

from app.database.session import get_db
from app.core.security import verify_password, create_access_token
from app.dependencies import get_current_user
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.schemas.auth import Token, UserMeResponse, PermissionDetail, LoginRequest
from app.schemas.common import APIResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/login", response_model=APIResponse)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    # Retrieve employee by username
    query = (
        select(Employee)
        .options(
            joinedload(Employee.employee_roles).joinedload(EmployeeRole.role)
        )
        .where(Employee.username == login_data.username)
    )
    employee = db.scalars(query).unique().first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )

    if not verify_password(login_data.password, employee.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is deactivated",
        )

    access_token = create_access_token(subject=employee.id)

    # Update last login timestamp
    employee.last_login_at = datetime.now(timezone.utc)
    db.add(employee)
    db.commit()

    return APIResponse(
        success=True,
        message="Login successful",
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "employee": {
                "id": str(employee.id),
                "employee_code": employee.employee_code,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "email": employee.email,
                "username": employee.username,
            }
        },
    )


@router.get("/me", response_model=APIResponse)
def get_me(
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        user_uuid = UUID(current_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token credentials",
        )

    query = (
        select(Employee)
        .options(
            joinedload(Employee.employee_roles)
            .joinedload(EmployeeRole.role)
            .joinedload(Role.permissions)
        )
        .where(Employee.id == user_uuid)
    )
    employee = db.scalars(query).unique().first()

    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Resolve active roles — collect both names and codes
    roles = []
    role_codes = []
    permissions_map = {}

    for er in employee.employee_roles:
        if er.is_active and er.role:
            roles.append(er.role.name)
            role_codes.append(er.role.role_code)
            for p in er.role.permissions:
                mod = p.module_name
                if mod not in permissions_map:
                    permissions_map[mod] = {
                        "can_view": False,
                        "can_create": False,
                        "can_edit": False,
                        "can_delete": False,
                        "can_approve": False,
                        "can_export": False,
                    }
                # Logical OR to aggregate permissions from multiple roles
                permissions_map[mod]["can_view"] |= p.can_view
                permissions_map[mod]["can_create"] |= p.can_create
                permissions_map[mod]["can_edit"] |= p.can_edit
                permissions_map[mod]["can_delete"] |= p.can_delete
                permissions_map[mod]["can_approve"] |= p.can_approve
                permissions_map[mod]["can_export"] |= p.can_export

    # Super-admin bypass: ADMIN or CEO role codes get full access on all modules
    SUPER_ADMIN_CODES = {"ADMIN", "CEO", "CHIEF_EXECUTIVE_OFFICER", "ADMINISTRATOR"}
    if set(role_codes) & SUPER_ADMIN_CODES:
        for mod in ["HR", "Clients", "Finance", "Projects", "Inventory", "Settings", "Reports", "Timesheets", "Tasks"]:
            permissions_map[mod] = {
                "can_view": True,
                "can_create": True,
                "can_edit": True,
                "can_delete": True,
                "can_approve": True,
                "can_export": True,
            }

    permissions_list = [
        PermissionDetail(
            module_name=mod,
            can_view=perms["can_view"],
            can_create=perms["can_create"],
            can_edit=perms["can_edit"],
            can_delete=perms["can_delete"],
            can_approve=perms["can_approve"],
            can_export=perms["can_export"],
        )
        for mod, perms in permissions_map.items()
    ]

    me_data = UserMeResponse(
        id=employee.id,
        employee_code=employee.employee_code,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        username=employee.username,
        is_active=employee.is_active,
        roles=roles,
        permissions=permissions_list,
    )

    return APIResponse(
        success=True,
        message="User profile retrieved successfully",
        data=me_data.model_dump(),
    )
