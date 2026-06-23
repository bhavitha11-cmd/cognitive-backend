from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):

    def get_by_id(self, id: UUID) -> Project | None:
        stmt = (
            select(Project)
            .options(
                joinedload(Project.client),
                joinedload(Project.project_manager),
            )
            .where(Project.id == id, Project.is_active == True)  # noqa: E712
        )
        return self.db.scalars(stmt).unique().first()

    def get_by_code(self, code: str) -> Project | None:
        return self.db.scalars(
            select(Project).where(Project.project_code == code)
        ).first()

    def get_by_name_and_client(self, name: str, client_id: UUID) -> Project | None:
        return self.db.scalars(
            select(Project).where(
                and_(
                    Project.name.ilike(name),
                    Project.client_id == client_id,
                )
            )
        ).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
        is_active: bool | None = True,
    ) -> list[Project]:
        stmt = select(Project).options(
            joinedload(Project.client),
            joinedload(Project.project_manager),
        )
        stmt = self._apply_filters(stmt, search, client_id, status, is_active)
        stmt = stmt.order_by(Project.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).unique().all())

    def count(
        self,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
        is_active: bool | None = True,
    ) -> int:
        stmt = select(func.count(Project.id))
        stmt = self._apply_filters(stmt, search, client_id, status, is_active)
        return self.db.scalar(stmt) or 0

    def _apply_filters(self, stmt, search, client_id, status, is_active):
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Project.name.ilike(pattern),
                    Project.project_code.ilike(pattern),
                )
            )
        if client_id is not None:
            stmt = stmt.where(Project.client_id == client_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if is_active is not None:
            stmt = stmt.where(Project.is_active == is_active)
        return stmt

    # ── Row-Level Scoped Queries (RBAC) ──────────────────────────────────────

    def _apply_scope_filter(self, stmt, user_context):
        """Apply row-level RBAC filtering based on DataAccessLevel."""
        from app.core.rbac import DataAccessLevel
        from app.models.task import Task
        from app.models.task_assignment import TaskAssignment

        level = user_context.data_access_level
        uid = user_context.employee_id

        if level == DataAccessLevel.FULL:
            return stmt  # No filter — sees everything

        if level == DataAccessLevel.MANAGED:
            # Projects where user is PM or creator
            return stmt.where(
                or_(
                    Project.project_manager_id == uid,
                    Project.created_by == uid,
                )
            )

        if level == DataAccessLevel.TEAM:
            # Projects where user is PM, creator, or project member
            member_subq = (
                select(ProjectMember.project_id)
                .where(
                    ProjectMember.employee_id == uid,
                    ProjectMember.left_at.is_(None),
                )
            )
            return stmt.where(
                or_(
                    Project.project_manager_id == uid,
                    Project.created_by == uid,
                    Project.id.in_(member_subq),
                )
            )

        # SELF — projects where user is PM, creator, a member, or has task assignments
        member_subq = (
            select(ProjectMember.project_id)
            .where(
                ProjectMember.employee_id == uid,
                ProjectMember.left_at.is_(None),
            )
        )
        assigned_project_subq = (
            select(Task.project_id).distinct()
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == uid,
                TaskAssignment.status != "CANCELLED",
                Task.is_active == True,  # noqa: E712
            )
        )
        return stmt.where(
            or_(
                Project.project_manager_id == uid,
                Project.created_by == uid,
                Project.id.in_(member_subq),
                Project.id.in_(assigned_project_subq),
            )
        )

    def get_all_scoped(
        self,
        user_context,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
        is_active: bool | None = True,
    ) -> list[Project]:
        stmt = select(Project).options(
            joinedload(Project.client),
            joinedload(Project.project_manager),
        )
        stmt = self._apply_filters(stmt, search, client_id, status, is_active)
        stmt = self._apply_scope_filter(stmt, user_context)
        stmt = stmt.order_by(Project.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).unique().all())

    def count_scoped(
        self,
        user_context,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
        is_active: bool | None = True,
    ) -> int:
        stmt = select(func.count(Project.id))
        stmt = self._apply_filters(stmt, search, client_id, status, is_active)
        stmt = self._apply_scope_filter(stmt, user_context)
        return self.db.scalar(stmt) or 0

    def is_visible_to_user(self, project_id: UUID, user_context) -> bool:
        """Check if a specific project is visible to the user."""
        from app.core.rbac import DataAccessLevel
        if user_context.data_access_level == DataAccessLevel.FULL:
            return True
        stmt = select(func.count(Project.id)).where(Project.id == project_id, Project.is_active == True)
        stmt = self._apply_scope_filter(stmt, user_context)
        return (self.db.scalar(stmt) or 0) > 0

    # ── Project Member helpers ────────────────────────────────────────────────

    def get_members(self, project_id: UUID) -> list[ProjectMember]:
        from sqlalchemy.orm import joinedload as jl
        from app.models.employee import Employee
        stmt = (
            select(ProjectMember)
            .options(jl(ProjectMember.employee))
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.left_at.is_(None),
            )
            .order_by(ProjectMember.joined_at)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get_member_by_id(self, member_id: UUID) -> ProjectMember | None:
        return self.db.scalars(
            select(ProjectMember).where(ProjectMember.id == member_id)
        ).first()

    def get_active_member(self, project_id: UUID, employee_id: UUID) -> ProjectMember | None:
        return self.db.scalars(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.employee_id == employee_id,
                ProjectMember.left_at.is_(None),
            )
        ).first()

    def add_member(self, data: dict) -> ProjectMember:
        member = ProjectMember(**data)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, member: ProjectMember) -> None:
        from datetime import datetime, timezone
        member.left_at = datetime.now(timezone.utc)
        self.db.commit()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(self, data: dict) -> Project:
        project = Project(**data)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(self, project: Project, data: dict) -> Project:
        for key, value in data.items():
            setattr(project, key, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete_soft(self, project: Project) -> Project:
        project.is_active = False
        self.db.commit()
        self.db.refresh(project)
        return project

