from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository):

    def get_by_id(self, id: UUID, load_assignments: bool = False) -> Task | None:
        stmt = select(Task).where(Task.id == id)
        if load_assignments:
            stmt = stmt.options(
                selectinload(Task.assignments).joinedload(TaskAssignment.employee),
                selectinload(Task.assignments).joinedload(TaskAssignment.assigner),
            )
        return self.db.scalars(stmt).unique().first()

    def get_by_code_and_project(self, code: str, project_id: UUID) -> Task | None:
        return self.db.scalars(
            select(Task).where(
                Task.task_code == code,
                Task.project_id == project_id,
            )
        ).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        project_id: UUID | None = None,
        status: str | None = None,
        dept_cat: str | None = None,
        search: str | None = None,
        is_active: bool | None = True,
    ) -> list[Task]:
        stmt = select(Task)
        stmt = self._apply_filters(stmt, project_id, status, dept_cat, search, is_active)
        stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).unique().all())

    def count(
        self,
        project_id: UUID | None = None,
        status: str | None = None,
        dept_cat: str | None = None,
        search: str | None = None,
        is_active: bool | None = True,
    ) -> int:
        stmt = select(func.count()).select_from(Task)
        stmt = self._apply_filters(stmt, project_id, status, dept_cat, search, is_active)
        return self.db.scalar(stmt) or 0

    def _apply_filters(self, stmt, project_id, status, dept_cat, search, is_active):
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if dept_cat is not None:
            stmt = stmt.where(Task.department_category == dept_cat)
        if is_active is not None:
            stmt = stmt.where(Task.is_active == is_active)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Task.task_code.ilike(pattern),
                    Task.title.ilike(pattern),
                    Task.description.ilike(pattern),
                )
            )
        return stmt

    def create(self, data: dict) -> Task:
        task = Task(**data)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def update(self, task: Task, data: dict) -> Task:
        for key, value in data.items():
            setattr(task, key, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    # ── Assignment helpers ─────────────────────────────────────────────────────

    def get_assignment(self, task_id: UUID, employee_id: UUID) -> TaskAssignment | None:
        return self.db.scalars(
            select(TaskAssignment).where(
                TaskAssignment.task_id == task_id,
                TaskAssignment.employee_id == employee_id,
                TaskAssignment.status != "CANCELLED",
            )
        ).first()

    def get_assignment_by_id(self, assignment_id: UUID) -> TaskAssignment | None:
        return self.db.scalars(
            select(TaskAssignment)
            .options(
                joinedload(TaskAssignment.employee),
                joinedload(TaskAssignment.assigner),
            )
            .where(TaskAssignment.id == assignment_id)
        ).unique().first()

    def get_assignments_by_task(self, task_id: UUID) -> list[TaskAssignment]:
        return list(
            self.db.scalars(
                select(TaskAssignment)
                .options(
                    joinedload(TaskAssignment.employee),
                    joinedload(TaskAssignment.assigner),
                )
                .where(TaskAssignment.task_id == task_id)
                .order_by(TaskAssignment.assigned_at.desc())
            ).unique().all()
        )

    def create_assignment(self, data: dict) -> TaskAssignment:
        assignment = TaskAssignment(**data)
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def update_assignment(self, assignment: TaskAssignment, data: dict) -> TaskAssignment:
        for key, value in data.items():
            setattr(assignment, key, value)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def get_tasks_by_project(self, project_id: UUID) -> list[Task]:
        return list(
            self.db.scalars(
                select(Task)
                .where(Task.project_id == project_id, Task.is_active == True)
                .order_by(Task.task_code)
            ).unique().all()
        )
