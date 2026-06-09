from uuid import UUID

from sqlalchemy import select

from app.models.department import Department
from app.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository):
    def get_all(self) -> list[Department]:
        return list(self.db.scalars(select(Department)).all())

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
