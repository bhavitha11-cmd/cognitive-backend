from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.designation import Designation
from app.repositories.designation_repository import DesignationRepository
from app.schemas.designation import DesignationCreate, DesignationUpdate, DesignationResponse


class DesignationService:
    def __init__(self, db: Session):
        self.repo = DesignationRepository(db)

    def get_all(self) -> list[DesignationResponse]:
        designations = self.repo.get_all()
        return [DesignationResponse.model_validate(d) for d in designations]

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
        designation = self.repo.create(data.model_dump())
        return DesignationResponse.model_validate(designation)

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
                raise ValueError(
                    f"Designation with code '{update_data['code']}' already exists"
                )

        designation = self.repo.update(designation, update_data)
        return DesignationResponse.model_validate(designation)

    def delete(self, id: UUID) -> None:
        designation = self.repo.get_by_id(id)
        if not designation:
            raise ValueError(f"Designation with id {id} not found")
        self.repo.delete(designation)

