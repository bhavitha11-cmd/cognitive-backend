from uuid import UUID

from sqlalchemy import func, select

from app.models.designation import Designation
from app.repositories.base import BaseRepository


class DesignationRepository(BaseRepository):
    def get_all(self) -> list[Designation]:
        return list(self.db.scalars(select(Designation)).all())

    def get_paginated(self, skip: int = 0, limit: int = 200) -> tuple[list[Designation], int]:
        total = self.db.scalar(select(func.count(Designation.id))) or 0
        items = list(self.db.scalars(select(Designation).offset(skip).limit(limit)).all())
        return items, total

    def get_by_id(self, id: UUID) -> Designation | None:
        return self.db.get(Designation, id)

    def get_by_department(self, department_id: UUID) -> list[Designation]:
        return list(
            self.db.scalars(
                select(Designation).where(Designation.department_id == department_id)
            ).all()
        )

    def create(self, data: dict) -> Designation:
        designation = Designation(**data)
        self.db.add(designation)
        self.db.commit()
        self.db.refresh(designation)
        return designation

    def update(self, designation: Designation, data: dict) -> Designation:
        for key, value in data.items():
            setattr(designation, key, value)
        self.db.commit()
        self.db.refresh(designation)
        return designation

    def delete(self, designation: Designation) -> None:
        self.db.delete(designation)
        self.db.commit()
