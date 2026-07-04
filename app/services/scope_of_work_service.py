from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scope_of_work import ScopeOfWork
from app.schemas.scope_of_work import (
    ScopeCreate,
    ScopeLookupItem,
    ScopeResponse,
    ScopeUpdate,
)
from app.services.audit_service import AuditService


class ScopeService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_404(self, id: UUID) -> ScopeOfWork:
        scope = self.db.get(ScopeOfWork, id)
        if not scope:
            raise ValueError(f"Scope of work with id {id} not found")
        return scope

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_all(
        self,
        department_category: str | None = None,
        include_inactive: bool = False,
    ) -> list[ScopeResponse]:
        stmt = select(ScopeOfWork)
        if not include_inactive:
            stmt = stmt.where(ScopeOfWork.is_active.is_(True))
        if department_category:
            stmt = stmt.where(ScopeOfWork.department_category == department_category)
        stmt = stmt.order_by(ScopeOfWork.department_category, ScopeOfWork.name)
        scopes = list(self.db.scalars(stmt).all())
        return [ScopeResponse.model_validate(s) for s in scopes]

    def get_by_id(self, id: UUID) -> ScopeResponse:
        scope = self._get_or_404(id)
        return ScopeResponse.model_validate(scope)

    def get_lookup(self, limit: int = 100) -> list[ScopeLookupItem]:
        stmt = (
            select(ScopeOfWork.id, ScopeOfWork.code, ScopeOfWork.name)
            .where(ScopeOfWork.is_active == True)
            .order_by(ScopeOfWork.name)
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [ScopeLookupItem(id=r.id, code=r.code, name=r.name) for r in rows]

    def create(self, data: ScopeCreate) -> ScopeResponse:
        # Check code uniqueness
        existing_code = self.db.scalars(
            select(ScopeOfWork).where(ScopeOfWork.code == data.code)
        ).first()
        if existing_code:
            raise ValueError(f"Scope of work with code '{data.code}' already exists")

        # Check name uniqueness within the same department_category
        existing_name = self.db.scalars(
            select(ScopeOfWork).where(
                ScopeOfWork.name == data.name,
                ScopeOfWork.department_category == data.department_category,
            )
        ).first()
        if existing_name:
            raise ValueError(
                f"Scope of work with name '{data.name}' already exists "
                f"in department category '{data.department_category}'"
            )

        try:
            scope = ScopeOfWork(**data.model_dump())
            self.db.add(scope)
            self.db.commit()
            self.db.refresh(scope)
            AuditService.log(
                self.db,
                "scope_of_work",
                scope.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={"code": scope.code, "name": scope.name},
            )
            return ScopeResponse.model_validate(scope)
        except Exception:
            self.db.rollback()
            raise

    def update(self, id: UUID, data: ScopeUpdate) -> ScopeResponse:
        scope = self._get_or_404(id)
        update_data = data.model_dump(exclude_unset=True)

        if "code" in update_data and update_data["code"] != scope.code:
            if self.db.scalars(
                select(ScopeOfWork).where(
                    ScopeOfWork.code == update_data["code"],
                    ScopeOfWork.id != id,
                )
            ).first():
                raise ValueError(
                    f"Scope of work with code '{update_data['code']}' already exists"
                )

        if "name" in update_data:
            target_category = update_data.get("department_category", scope.department_category)
            if self.db.scalars(
                select(ScopeOfWork).where(
                    ScopeOfWork.name == update_data["name"],
                    ScopeOfWork.department_category == target_category,
                    ScopeOfWork.id != id,
                )
            ).first():
                raise ValueError(
                    f"Scope of work with name '{update_data['name']}' already exists "
                    f"in department category '{target_category}'"
                )

        old_values = {k: getattr(scope, k, None) for k in update_data}
        try:
            for key, value in update_data.items():
                setattr(scope, key, value)
            self.db.commit()
            self.db.refresh(scope)
            AuditService.log(
                self.db,
                "scope_of_work",
                id,
                "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            return ScopeResponse.model_validate(scope)
        except Exception:
            self.db.rollback()
            raise

    def delete(self, id: UUID) -> None:
        scope = self._get_or_404(id)

        # Soft delete — check no tasks are assigned
        # Task model may not exist yet; guard with a try/except to avoid import errors
        # during early migration stages.
        try:
            from app.models.task import Task  # noqa: PLC0415

            from sqlalchemy import func

            task_count = self.db.scalar(
                select(func.count(Task.id)).where(Task.scope_id == id)
            ) or 0
            if task_count:
                raise ValueError(
                    f"Cannot delete scope '{scope.name}': {task_count} task(s) are assigned. "
                    "Reassign or remove them first."
                )
        except ImportError:
            pass  # Task model not yet available; skip the check

        try:
            AuditService.log(
                self.db,
                "scope_of_work",
                id,
                "DELETE",
                performed_by=self.current_user_id,
                old_value={"code": scope.code, "name": scope.name},
            )
            # Soft delete
            scope.is_active = False
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
