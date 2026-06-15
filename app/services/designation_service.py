from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.designation import Designation
from app.models.employee import Employee
from app.repositories.designation_repository import DesignationRepository
from app.schemas.designation import DesignationCreate, DesignationUpdate, DesignationResponse
from app.services.audit_service import AuditService


class DesignationService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.repo = DesignationRepository(db)
        self.current_user_id = current_user_id

    def get_all(self, skip: int = 0, limit: int = 500) -> tuple[list[DesignationResponse], int]:
        desigs, total = self.repo.get_paginated(skip, limit)
        return [DesignationResponse.model_validate(d) for d in desigs], total

    def get_by_id(self, id: UUID) -> DesignationResponse:
        designation = self.repo.get_by_id(id)
        if not designation:
            raise ValueError(f"Designation with id {id} not found")
        return DesignationResponse.model_validate(designation)

    def get_by_department(self, department_id: UUID) -> list[DesignationResponse]:
        designations = self.repo.get_by_department(department_id)
        return [DesignationResponse.model_validate(d) for d in designations]

    def create(self, data: DesignationCreate) -> DesignationResponse:
        if self.repo.db.scalars(
            select(Designation).where(Designation.code == data.code)
        ).first():
            raise ValueError(f"Designation with code '{data.code}' already exists")

        try:
            designation = self.repo.create(data.model_dump())
            AuditService.log(
                self.repo.db, "designation", designation.id, "CREATE",
                performed_by=self.current_user_id,
                new_value={"name": designation.name, "code": designation.code},
            )
            return DesignationResponse.model_validate(designation)
        except Exception:
            self.repo.db.rollback()
            raise

    def update(self, id: UUID, data: DesignationUpdate) -> DesignationResponse:
        designation = self.repo.get_by_id(id)
        if not designation:
            raise ValueError(f"Designation with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "code" in update_data and update_data["code"] != designation.code:
            if self.repo.db.scalars(
                select(Designation).where(
                    Designation.code == update_data["code"], Designation.id != id
                )
            ).first():
                raise ValueError(f"Designation with code '{update_data['code']}' already exists")

        old_values = {k: getattr(designation, k, None) for k in update_data}
        try:
            designation = self.repo.update(designation, update_data)
            AuditService.log(
                self.repo.db, "designation", id, "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            return DesignationResponse.model_validate(designation)
        except Exception:
            self.repo.db.rollback()
            raise

    def delete(self, id: UUID) -> None:
        designation = self.repo.get_by_id(id)
        if not designation:
            raise ValueError(f"Designation with id {id} not found")

        # Block delete if employees are assigned
        count = self.repo.db.scalar(
            select(func.count(Employee.id)).where(Employee.designation_id == id)
        ) or 0
        if count:
            raise ValueError(
                f"Cannot delete designation '{designation.name}': {count} employee(s) are assigned. "
                f"Reassign them first."
            )

        try:
            AuditService.log(
                self.repo.db, "designation", id, "DELETE",
                performed_by=self.current_user_id,
                old_value={"name": designation.name, "code": designation.code},
            )
            self.repo.delete(designation)
        except Exception:
            self.repo.db.rollback()
            raise
