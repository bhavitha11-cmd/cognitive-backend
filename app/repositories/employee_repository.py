from uuid import UUID

from sqlalchemy import select

from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.department import Department
from app.models.team_member import TeamMember
from app.repositories.base import BaseRepository


class EmployeeRepository(BaseRepository):
    def get_all(self) -> list[Employee]:
        return list(self.db.scalars(select(Employee)).all())

    def get_by_id(self, id: UUID) -> Employee | None:
        return self.db.get(Employee, id)

    def get_by_email(self, email: str) -> Employee | None:
        return self.db.scalars(
            select(Employee).where(Employee.email == email)
        ).first()

    def get_by_username(self, username: str) -> Employee | None:
        return self.db.scalars(
            select(Employee).where(Employee.username == username)
        ).first()

    def get_by_employee_code(self, code: str) -> Employee | None:
        return self.db.scalars(
            select(Employee).where(Employee.employee_code == code)
        ).first()

    def get_direct_reports(self, employee_id: UUID) -> list[Employee]:
        return list(
            self.db.scalars(
                select(Employee).where(Employee.reporting_manager_id == employee_id)
            ).all()
        )

    def get_managed_teams(self, employee_id: UUID) -> list[TeamMember]:
        return list(
            self.db.scalars(
                select(TeamMember).where(
                    TeamMember.employee_id == employee_id,
                    TeamMember.role_in_team == "LEAD",
                    TeamMember.left_at.is_(None),
                )
            ).all()
        )

    def get_headed_departments(self, employee_id: UUID) -> list[Department]:
        return list(
            self.db.scalars(
                select(Department).where(Department.department_head_id == employee_id)
            ).all()
        )

    def get_all_managers(self) -> list[Employee]:
        return list(
            self.db.scalars(
                select(Employee).where(
                    Employee.reporting_manager_id.isnot(None),
                    Employee.is_active == True,
                )
            ).all()
        )

    def create(self, data: dict) -> Employee:
        employee = Employee(**data)
        self.db.add(employee)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def update(self, employee: Employee, data: dict) -> Employee:
        for key, value in data.items():
            setattr(employee, key, value)
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def delete(self, employee: Employee) -> None:
        self.db.delete(employee)
        self.db.commit()

    def get_lookup(self, limit: int = 200) -> list[Employee]:
        from sqlalchemy.orm import joinedload
        stmt = (
            select(Employee)
            .options(
                joinedload(Employee.employee_roles),
                joinedload(Employee.team_assignments)
            )
            .where(Employee.is_active == True)
            .order_by(Employee.first_name, Employee.last_name)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def get_employee_roles(self, employee_id: UUID) -> list[EmployeeRole]:
        return list(
            self.db.scalars(
                select(EmployeeRole).where(EmployeeRole.employee_id == employee_id)
            ).all()
        )

    def assign_role(self, employee_id: UUID, role_id: UUID) -> EmployeeRole:
        employee_role = EmployeeRole(employee_id=employee_id, role_id=role_id)
        self.db.add(employee_role)
        self.db.commit()
        self.db.refresh(employee_role)
        return employee_role

    def remove_role(self, employee_role_id: UUID) -> None:
        employee_role = self.db.get(EmployeeRole, employee_role_id)
        if employee_role:
            self.db.delete(employee_role)
            self.db.commit()
