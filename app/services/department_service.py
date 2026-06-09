from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department
from app.repositories.department_repository import DepartmentRepository
from app.schemas.department import DepartmentCreate, DepartmentUpdate, DepartmentResponse


class DepartmentService:
    def __init__(self, db: Session):
        self.repo = DepartmentRepository(db)

    def get_all(self) -> list[DepartmentResponse]:
        departments = self.repo.get_all()
        return [DepartmentResponse.model_validate(d) for d in departments]

    def get_by_id(self, id: UUID) -> DepartmentResponse:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")
        return DepartmentResponse.model_validate(department)

    def create(self, data: DepartmentCreate) -> DepartmentResponse:
        if self.repo.db.scalars(
            select(Department).where(Department.name == data.name)
        ).first():
            raise ValueError(f"Department with name '{data.name}' already exists")
        if self.repo.db.scalars(
            select(Department).where(Department.code == data.code)
        ).first():
            raise ValueError(f"Department with code '{data.code}' already exists")
        department = self.repo.create(data.model_dump())
        return DepartmentResponse.model_validate(department)

    def update(self, id: UUID, data: DepartmentUpdate) -> DepartmentResponse:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] != department.name:
            if self.repo.db.scalars(
                select(Department).where(
                    Department.name == update_data["name"], Department.id != id
                )
            ).first():
                raise ValueError(
                    f"Department with name '{update_data['name']}' already exists"
                )

        if "code" in update_data and update_data["code"] != department.code:
            if self.repo.db.scalars(
                select(Department).where(
                    Department.code == update_data["code"], Department.id != id
                )
            ).first():
                raise ValueError(
                    f"Department with code '{update_data['code']}' already exists"
                )

        department = self.repo.update(department, update_data)
        return DepartmentResponse.model_validate(department)

    def delete(self, id: UUID) -> None:
        department = self.repo.get_by_id(id)
        if not department:
            raise ValueError(f"Department with id {id} not found")
        self.repo.delete(department)
