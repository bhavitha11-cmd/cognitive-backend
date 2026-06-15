from uuid import UUID

from sqlalchemy import func, select

from app.models.department import Department
from app.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository):
    def get_all(self) -> list[Department]:
        return list(self.db.scalars(select(Department)).all())

    def get_paginated(self, skip: int = 0, limit: int = 200) -> tuple[list[Department], int]:
        total = self.db.scalar(select(func.count(Department.id))) or 0
        items = list(self.db.scalars(select(Department).offset(skip).limit(limit)).all())
        return items, total

    def get_by_id(self, id: UUID) -> Department | None:
        return self.db.get(Department, id)

    def create(self, data: dict) -> Department:
        department = Department(**data)
        self.db.add(department)
        self.db.commit()
        self.db.refresh(department)
        return department

    def update(self, department: Department, data: dict) -> Department:
        for key, value in data.items():
            setattr(department, key, value)
        self.db.commit()
        self.db.refresh(department)
        return department

    def delete(self, department: Department) -> None:
        self.db.delete(department)
        self.db.commit()
