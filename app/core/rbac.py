"""
Enterprise RBAC Engine — Row-level data access control.

Provides a 4-tier data access hierarchy:
  FULL     → Admin/CEO: sees everything
  MANAGED  → Manager: sees projects they manage or created
  TEAM     → Team Lead: sees projects they are a member of, manage, or created
  SELF     → Engineer: sees only tasks assigned to them
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import SUPER_ADMIN_CODES
from app.database.session import get_db
from app.dependencies import get_current_user

# Access level priority (higher number = more access)
_ACCESS_PRIORITY = {"SELF": 0, "TEAM": 1, "MANAGED": 2, "FULL": 3}


class DataAccessLevel(str, enum.Enum):
    """Defines the scope of data a user can see."""
    FULL = "FULL"          # Admin / CEO — sees everything
    MANAGED = "MANAGED"    # Manager — sees projects they manage or created
    TEAM = "TEAM"          # Team Lead — sees projects they are member of
    SELF = "SELF"          # Engineer — sees only assigned tasks

    @property
    def priority(self) -> int:
        return _ACCESS_PRIORITY[self.value]

    def __ge__(self, other: "DataAccessLevel") -> bool:
        return self.priority >= other.priority

    def __gt__(self, other: "DataAccessLevel") -> bool:
        return self.priority > other.priority

    def __le__(self, other: "DataAccessLevel") -> bool:
        return self.priority <= other.priority

    def __lt__(self, other: "DataAccessLevel") -> bool:
        return self.priority < other.priority


VALID_ACCESS_LEVELS = {e.value for e in DataAccessLevel}


@dataclass
class UserContext:
    """Resolved user identity + access scope for the current request."""
    employee_id: UUID
    role_codes: list[str] = field(default_factory=list)
    role_names: list[str] = field(default_factory=list)
    is_super_admin: bool = False
    data_access_level: DataAccessLevel = DataAccessLevel.SELF


def get_user_context(db: Session, user_id: str) -> UserContext:
    """
    Load the employee's active roles and resolve their effective data access level.
    Uses highest-privilege-wins strategy across all active roles.
    """
    from app.models.employee import Employee
    from app.models.employee_role import EmployeeRole
    from app.models.role import Role

    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity",
        )

    employee = db.scalars(
        select(Employee)
        .options(
            joinedload(Employee.employee_roles)
            .joinedload(EmployeeRole.role)
        )
        .where(Employee.id == user_uuid)
    ).unique().first()

    if not employee or not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or not found",
        )

    role_codes: list[str] = []
    role_names: list[str] = []
    is_super_admin = False
    highest_level = DataAccessLevel.SELF

    for er in employee.employee_roles:
        if not er.is_active or not er.role:
            continue

        role_codes.append(er.role.role_code)
        role_names.append(er.role.name)

        # Check super-admin status
        if er.role.role_code in SUPER_ADMIN_CODES or getattr(er.role, "is_super_admin", False):
            is_super_admin = True

        # Resolve data access level from the role's configured level
        role_level_str = getattr(er.role, "data_access_level", "SELF") or "SELF"
        try:
            role_level = DataAccessLevel(role_level_str)
        except ValueError:
            role_level = DataAccessLevel.SELF

        if role_level > highest_level:
            highest_level = role_level

    # Super-admins always get FULL access regardless of role configuration
    if is_super_admin:
        highest_level = DataAccessLevel.FULL

    return UserContext(
        employee_id=user_uuid,
        role_codes=role_codes,
        role_names=role_names,
        is_super_admin=is_super_admin,
        data_access_level=highest_level,
    )


# ── FastAPI Dependencies ─────────────────────────────────────────────────────


async def require_data_access(
    current_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserContext:
    """
    FastAPI dependency that resolves and injects UserContext.
    Use this in endpoint signatures to get the current user's RBAC context.
    """
    return get_user_context(db, current_user_id)
