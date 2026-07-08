"""
Central Authorization Engine for Cognitive ERP.

This is the single source of truth for all authorization decisions across the
entire ERP platform. Every module (Projects, Tasks, Attendance, Leave, HR,
Settings, and any future modules) delegates permission checking to this engine.

The engine provides three main APIs:

1. has_permission()       — Boolean gate: can the user do this action at all?
2. build_access_filter()  — Query-level filter: restrict a SQLAlchemy query
                            to only records the user is allowed to see.
3. can_access_record()    — Record-level check: can the user access this
                            specific record?
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, or_, literal, false as sa_false, true as sa_true
from sqlalchemy.orm import Session

from app.core.permission_scope import PermissionScope, PermissionAction
from app.core.config import SUPER_ADMIN_CODES
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.feature import Feature

logger = logging.getLogger(__name__)


class AuthorizationEngine:
    """Stateless authorization engine — instantiate with a db session."""

    def __init__(self, db: Session):
        self.db = db

    # ── 1. Boolean Gate ──────────────────────────────────────────────────────

    def has_permission(self, user_id: UUID, feature_key: str, action: str) -> bool:
        """Return True if the user has any scope other than NONE for the given
        feature + action combination.  Super-admins always return True."""
        if self._is_super_admin(user_id):
            return True

        scope = self._resolve_scope(user_id, feature_key, action)
        return PermissionScope.has_access(scope)

    # ── 2. Query-Level Filter ────────────────────────────────────────────────

    def build_access_filter(
        self,
        user_id: UUID,
        feature_key: str,
        action: str,
        *,
        owner_column=None,
        creator_column=None,
        department_column=None,
    ):
        """Return a SQLAlchemy filter clause that restricts a query to only
        records the user is allowed to access.

        Parameters
        ----------
        user_id : UUID
            The authenticated user's ID.
        feature_key : str
            The feature key (e.g. "projects", "tasks", "attendance").
        action : str
            The CRUD action (e.g. "view", "create", "update", "delete").
        owner_column : Column, optional
            The SQLAlchemy column representing record ownership
            (e.g. `Project.project_manager_id`, `Task.employee_id`).
        creator_column : Column, optional
            The SQLAlchemy column representing record creator
            (e.g. `Project.created_by`).
        department_column : Column, optional
            The SQLAlchemy column for department filtering
            (e.g. `Employee.department_id`).

        Returns
        -------
        A SQLAlchemy filter clause (BooleanClauseList) that can be passed to
        `.where()` or `.filter()`.
        """
        if self._is_super_admin(user_id):
            return sa_true()

        scope = self._resolve_scope(user_id, feature_key, action)

        if scope == PermissionScope.NONE.value:
            return sa_false()

        if scope in (PermissionScope.ALL.value, PermissionScope.COMPANY.value):
            return sa_true()

        if scope == PermissionScope.OWNED.value:
            if owner_column is not None:
                return owner_column == user_id
            return sa_false()

        if scope == PermissionScope.ADDED.value:
            if creator_column is not None:
                return creator_column == user_id
            return sa_false()

        if scope == PermissionScope.ADDED_OWNED.value:
            clauses = []
            if owner_column is not None:
                clauses.append(owner_column == user_id)
            if creator_column is not None:
                clauses.append(creator_column == user_id)
            return or_(*clauses) if clauses else sa_false()

        if scope == PermissionScope.TEAM.value:
            subordinate_ids = self._get_team_ids(user_id)
            if owner_column is not None:
                return owner_column.in_(subordinate_ids)
            if creator_column is not None:
                return creator_column.in_(subordinate_ids)
            return sa_false()

        if scope == PermissionScope.DEPARTMENT.value:
            dept_member_ids = self._get_department_member_ids(user_id)
            if department_column is not None:
                user_dept_id = self._get_user_department_id(user_id)
                if user_dept_id:
                    return department_column == user_dept_id
            if owner_column is not None:
                return owner_column.in_(dept_member_ids)
            if creator_column is not None:
                return creator_column.in_(dept_member_ids)
            return sa_false()

        # Unknown scope — deny by default
        logger.warning(f"Unknown scope '{scope}' for user={user_id}, feature={feature_key}")
        return sa_false()

    # ── 3. Record-Level Check ────────────────────────────────────────────────

    def can_access_record(
        self,
        user_id: UUID,
        feature_key: str,
        action: str,
        *,
        record_owner_id: UUID | None = None,
        record_creator_id: UUID | None = None,
        record_department_id: UUID | None = None,
    ) -> bool:
        """Check if the user can access a specific record based on ownership,
        creator, team membership, or department."""
        if self._is_super_admin(user_id):
            return True

        scope = self._resolve_scope(user_id, feature_key, action)

        if scope == PermissionScope.NONE.value:
            return False

        if scope in (PermissionScope.ALL.value, PermissionScope.COMPANY.value):
            return True

        if scope == PermissionScope.OWNED.value:
            return record_owner_id == user_id

        if scope == PermissionScope.ADDED.value:
            return record_creator_id == user_id

        if scope == PermissionScope.ADDED_OWNED.value:
            return record_owner_id == user_id or record_creator_id == user_id

        if scope == PermissionScope.TEAM.value:
            subordinate_ids = self._get_team_ids(user_id)
            target_id = record_owner_id or record_creator_id
            return target_id in subordinate_ids if target_id else False

        if scope == PermissionScope.DEPARTMENT.value:
            dept_member_ids = self._get_department_member_ids(user_id)
            target_id = record_owner_id or record_creator_id
            if target_id and target_id in dept_member_ids:
                return True
            if record_department_id:
                user_dept_id = self._get_user_department_id(user_id)
                return record_department_id == user_dept_id
            return False

        return False

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _is_super_admin(self, user_id: UUID) -> bool:
        """Check if the user holds any super-admin role."""
        role_codes = self.db.scalars(
            select(Role.role_code)
            .join(EmployeeRole, EmployeeRole.role_id == Role.id)
            .where(
                EmployeeRole.employee_id == user_id,
                EmployeeRole.is_active == True,
                Role.is_active == True,
            )
        ).all()
        return any(code in SUPER_ADMIN_CODES for code in role_codes)

    def _resolve_scope(self, user_id: UUID, feature_key: str, action: str) -> str:
        """Look up the highest-privilege scope for this user × feature × action.

        A user may hold multiple roles, each with a different scope for the same
        feature. We return the *broadest* scope (highest privilege).
        """
        scope_column_map = {
            PermissionAction.VIEW.value: RolePermission.view_scope,
            PermissionAction.CREATE.value: RolePermission.create_scope,
            PermissionAction.UPDATE.value: RolePermission.update_scope,
            PermissionAction.DELETE.value: RolePermission.delete_scope,
            # Legacy aliases
            "edit": RolePermission.update_scope,
            "activate": RolePermission.delete_scope,
        }
        scope_col = scope_column_map.get(action)
        if scope_col is None:
            return PermissionScope.NONE.value

        scopes = self.db.scalars(
            select(scope_col)
            .join(Feature, Feature.id == RolePermission.feature_id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(EmployeeRole, EmployeeRole.role_id == Role.id)
            .where(
                EmployeeRole.employee_id == user_id,
                EmployeeRole.is_active == True,
                Role.is_active == True,
                Feature.feature_key == feature_key,
            )
        ).all()

        if not scopes:
            return PermissionScope.NONE.value

        # Return the broadest scope
        priority = [
            PermissionScope.NONE.value,
            PermissionScope.OWNED.value,
            PermissionScope.ADDED.value,
            PermissionScope.ADDED_OWNED.value,
            PermissionScope.TEAM.value,
            PermissionScope.DEPARTMENT.value,
            PermissionScope.COMPANY.value,
            PermissionScope.ALL.value,
        ]
        best = PermissionScope.NONE.value
        for s in scopes:
            if s in priority and priority.index(s) > priority.index(best):
                best = s
        return best

    def _get_team_ids(self, user_id: UUID) -> set[UUID]:
        """Return the set of employee IDs in the user's reporting hierarchy
        (including the user themselves). Uses OrganizationHierarchyService."""
        from app.services.organization_hierarchy_service import OrganizationHierarchyService
        hierarchy_svc = OrganizationHierarchyService(self.db)
        return hierarchy_svc.get_visible_employee_ids(user_id)

    def _get_user_department_id(self, user_id: UUID) -> UUID | None:
        """Return the user's department ID."""
        return self.db.scalar(
            select(Employee.department_id).where(Employee.id == user_id)
        )

    def _get_department_member_ids(self, user_id: UUID) -> set[UUID]:
        """Return all active employee IDs in the user's department."""
        dept_id = self._get_user_department_id(user_id)
        if not dept_id:
            return {user_id}
        ids = set(self.db.scalars(
            select(Employee.id).where(
                Employee.department_id == dept_id,
                Employee.is_active == True,
            )
        ).all())
        ids.add(user_id)
        return ids
