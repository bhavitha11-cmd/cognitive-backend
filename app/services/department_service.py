from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import (
    DepartmentCreate,
    DepartmentLookupItem,
    DepartmentUpdate,
    DepartmentResponse,
)
from app.services.audit_service import AuditService


class DepartmentService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.repo = DepartmentRepository(db)
        self.current_user_id = current_user_id

    def get_all(self, skip: int = 0, limit: int = 200) -> tuple[list[DepartmentResponse], int]:
        depts, total = self.repo.get_paginated(skip, limit)
        return [DepartmentResponse.model_validate(d) for d in depts], total

    def get_by_id(self, id: UUID) -> DepartmentResponse:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")
        return DepartmentResponse.model_validate(department)

    def get_lookup(self) -> list[DepartmentLookupItem]:
        rows = self.repo.get_lookup()
        return [
            DepartmentLookupItem(id=r.id, name=r.name, code=r.code)
            for r in rows
        ]

    def create(self, data: DepartmentCreate) -> DepartmentResponse:
        # Case-insensitive name uniqueness
        if self.repo.db.scalars(
            select(Department).where(Department.name.ilike(data.name))
        ).first():
            raise ValueError(f"Department with name '{data.name}' already exists")
        if self.repo.db.scalars(
            select(Department).where(Department.code.ilike(data.code))
        ).first():
            raise ValueError(f"Department with code '{data.code}' already exists")

        try:
            department = self.repo.create(data.model_dump())
            AuditService.log(
                self.repo.db, "department", department.id, "CREATE",
                performed_by=self.current_user_id,
                new_value={"name": department.name, "code": department.code},
            )
            return DepartmentResponse.model_validate(department)
        except Exception:
            self.repo.db.rollback()
            raise

    def update(self, id: UUID, data: DepartmentUpdate) -> DepartmentResponse:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"].lower() != department.name.lower():
            if self.repo.db.scalars(
                select(Department).where(
                    Department.name.ilike(update_data["name"]), Department.id != id
                )
            ).first():
                raise ValueError(f"Department with name '{update_data['name']}' already exists")

        if "code" in update_data and update_data["code"].lower() != department.code.lower():
            if self.repo.db.scalars(
                select(Department).where(
                    Department.code.ilike(update_data["code"]), Department.id != id
                )
            ).first():
                raise ValueError(f"Department with code '{update_data['code']}' already exists")

        old_values = {k: getattr(department, k, None) for k in update_data}
        try:
            department = self.repo.update(department, update_data)
            AuditService.log(
                self.repo.db, "department", id, "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            return DepartmentResponse.model_validate(department)
        except Exception:
            self.repo.db.rollback()
            raise

    def delete(self, id: UUID) -> None:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")

        # Block delete if employees are assigned
        count = self.repo.db.scalar(
            select(func.count(Employee.id)).where(Employee.department_id == id)
        ) or 0
        if count:
            raise ValueError(
                f"Cannot delete department '{department.name}': {count} employee(s) are assigned. "
                f"Reassign or offboard them first."
            )

        # Block delete if a department head is still set
        if department.department_head_id:
            raise ValueError(
                f"Cannot delete department '{department.name}': it still has a department head assigned. "
                f"Remove the department head first."
            )

        try:
            AuditService.log(
                self.repo.db, "department", id, "DELETE",
                performed_by=self.current_user_id,
                old_value={"name": department.name, "code": department.code},
            )
            # Soft delete: deactivate instead of removing the row
            self.repo.update(department, {"is_active": False})
        except Exception:
            self.repo.db.rollback()
            raise
