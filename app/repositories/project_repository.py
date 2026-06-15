from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):

    def get_by_id(self, id: UUID) -> Project | None:
        stmt = (
            select(Project)
            .options(
                joinedload(Project.client),
                joinedload(Project.project_manager),
            )
            .where(Project.id == id)
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
