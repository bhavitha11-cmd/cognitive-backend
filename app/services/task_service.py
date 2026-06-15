import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.repositories.task_repository import TaskRepository
from app.schemas.task import (
    TaskAssignmentCreate,
    TaskAssignmentResponse,
    TaskAssignmentUpdate,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.audit_service import AuditService


class TaskService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.repo = TaskRepository(db)
        self.current_user_id = current_user_id

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        project_id: UUID | None = None,
        status: str | None = None,
        dept_cat: str | None = None,
        search: str | None = None,
    ) -> tuple[list[TaskListResponse], int]:
        tasks = self.repo.get_all(
            skip=skip,
            limit=limit,
            project_id=project_id,
            status=status,
            dept_cat=dept_cat,
            search=search,
        )
        total = self.repo.count(
            project_id=project_id,
            status=status,
            dept_cat=dept_cat,
            search=search,
        )
        return [self._build_list_response(t) for t in tasks], total

    def get_by_id(self, id: UUID) -> TaskResponse:
        task = self.repo.get_by_id(id, load_assignments=True)
        if not task:
            raise ValueError(f"Task with id {id} not found")
        return self._build_response(task)

    def get_by_project(self, project_id: UUID) -> list[TaskListResponse]:
        tasks = self.repo.get_tasks_by_project(project_id)
        return [self._build_list_response(t) for t in tasks]

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(self, data: TaskCreate) -> TaskResponse:
        # Validate project exists and is in an acceptable state
        project = self._get_project(data.project_id)
        if not project:
            raise ValueError(f"Project with id {data.project_id} not found")
        if hasattr(project, "status") and project.status not in ("ACTIVE", "DRAFT", "active", "draft"):
            raise ValueError(
                f"Cannot add tasks to a project with status '{project.status}'. "
                "Project must be ACTIVE or DRAFT."
            )

        # Validate task_code uniqueness within project
        existing = self.repo.get_by_code_and_project(data.task_code, data.project_id)
        if existing:
            raise ValueError(
                f"Task code '{data.task_code}' already exists in this project"
            )

        # Auto-set department_category from scope if scope provided and dept not set
        dept_cat = data.department_category
        scope_name = None
        if data.scope_of_work_id:
            scope = self._get_scope(data.scope_of_work_id)
            if scope:
                scope_name = getattr(scope, "name", None) or getattr(scope, "scope_name", None)
                if not dept_cat and hasattr(scope, "department_category"):
                    dept_cat = scope.department_category

        task_data = data.model_dump()
        task_data["department_category"] = dept_cat
        if self.current_user_id:
            task_data["created_by"] = self.current_user_id

        task = self.repo.create(task_data)

        # Update task count on project if the project model supports it
        self._increment_project_task_count(project)

        AuditService.log(
            self.db, "task", task.id, "CREATE",
            performed_by=self.current_user_id,
            new_value={
                "task_code": task.task_code,
                "title": task.title,
                "project_id": str(task.project_id),
                "status": task.status,
            },
        )

        task = self.repo.get_by_id(task.id, load_assignments=True)
        return self._build_response(task)

    # ── Update ─────────────────────────────────────────────────────────────────

    def update(self, id: UUID, data: TaskUpdate) -> TaskResponse:
        task = self.repo.get_by_id(id, load_assignments=True)
        if not task:
            raise ValueError(f"Task with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        # Validate task_code uniqueness within project (excluding self)
        if "task_code" in update_data and update_data["task_code"] != task.task_code:
            existing = self.repo.get_by_code_and_project(
                update_data["task_code"], task.project_id
            )
            if existing and existing.id != id:
                raise ValueError(
                    f"Task code '{update_data['task_code']}' already exists in this project"
                )

        new_status = update_data.get("status")

        # Auto-manage dates and progress on status transitions
        if new_status and new_status != task.status:
            if new_status == "IN_PROGRESS":
                if not task.actual_start_date and "actual_start_date" not in update_data:
                    update_data["actual_start_date"] = date.today()
            elif new_status == "COMPLETED":
                if not task.actual_end_date and "actual_end_date" not in update_data:
                    update_data["actual_end_date"] = date.today()
                if "progress" not in update_data:
                    update_data["progress"] = 1.0

        old_values = {k: getattr(task, k, None) for k in update_data}
        task = self.repo.update(task, update_data)

        AuditService.log(
            self.db, "task", id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=update_data,
        )

        task = self.repo.get_by_id(id, load_assignments=True)
        return self._build_response(task)

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete(self, id: UUID) -> None:
        task = self.repo.get_by_id(id)
        if not task:
            raise ValueError(f"Task with id {id} not found")
        if task.status not in ("NOT_STARTED", "CANCELLED"):
            raise ValueError(
                f"Cannot delete a task with status '{task.status}'. "
                "Only NOT_STARTED or CANCELLED tasks can be deleted."
            )

        self.repo.update(task, {"is_active": False})

        AuditService.log(
            self.db, "task", id, "DELETE",
            performed_by=self.current_user_id,
            old_value={"task_code": task.task_code, "status": task.status},
        )

    # ── Assignments ────────────────────────────────────────────────────────────

    def assign_employee(
        self, task_id: UUID, data: TaskAssignmentCreate
    ) -> TaskAssignmentResponse:
        task = self.repo.get_by_id(task_id)
        if not task or not task.is_active:
            raise ValueError(f"Task with id {task_id} not found")

        employee = self.db.get(Employee, data.employee_id)
        if not employee:
            raise ValueError(f"Employee with id {data.employee_id} not found")
        if not employee.is_active:
            raise ValueError("Cannot assign an inactive employee to a task")

        existing = self.repo.get_assignment(task_id, data.employee_id)
        if existing:
            raise ValueError("Employee is already assigned to this task")

        assignment_data = {
            "task_id": task_id,
            "employee_id": data.employee_id,
            "assigned_by": self.current_user_id,
            "assigned_hours": data.assigned_hours,
            "planned_start_date": data.planned_start_date,
            "planned_end_date": data.planned_end_date,
            "notes": data.notes,
            "status": "ASSIGNED",
        }
        assignment = self.repo.create_assignment(assignment_data)

        AuditService.log(
            self.db, "task_assignment", assignment.id, "ASSIGN",
            performed_by=self.current_user_id,
            new_value={
                "task_id": str(task_id),
                "employee_id": str(data.employee_id),
            },
        )

        assignment = self.repo.get_assignment_by_id(assignment.id)
        return self._build_assignment_response(assignment)

    def update_assignment(
        self, task_id: UUID, assignment_id: UUID, data: TaskAssignmentUpdate
    ) -> TaskAssignmentResponse:
        assignment = self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise ValueError(f"Assignment with id {assignment_id} not found")
        if assignment.task_id != task_id:
            raise ValueError("Assignment does not belong to the specified task")

        update_data = data.model_dump(exclude_unset=True)

        # Auto-set completed_at when status changes to COMPLETED
        if update_data.get("status") == "COMPLETED" and not assignment.completed_at:
            update_data["completed_at"] = datetime.utcnow()

        old_values = {k: getattr(assignment, k, None) for k in update_data}
        assignment = self.repo.update_assignment(assignment, update_data)

        AuditService.log(
            self.db, "task_assignment", assignment_id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=update_data,
        )

        assignment = self.repo.get_assignment_by_id(assignment_id)
        return self._build_assignment_response(assignment)

    def remove_assignment(self, task_id: UUID, assignment_id: UUID) -> None:
        assignment = self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise ValueError(f"Assignment with id {assignment_id} not found")
        if assignment.task_id != task_id:
            raise ValueError("Assignment does not belong to the specified task")

        self.repo.update_assignment(assignment, {"status": "CANCELLED"})

        AuditService.log(
            self.db, "task_assignment", assignment_id, "REMOVE",
            performed_by=self.current_user_id,
            old_value={
                "task_id": str(task_id),
                "employee_id": str(assignment.employee_id),
            },
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_project(self, project_id: UUID):
        try:
            from app.models.project import Project
            return self.db.get(Project, project_id)
        except Exception:
            return None

    def _get_scope(self, scope_id: UUID):
        try:
            from app.models.scope_of_work import ScopeOfWork
            return self.db.get(ScopeOfWork, scope_id)
        except Exception:
            return None

    def _increment_project_task_count(self, project) -> None:
        try:
            if hasattr(project, "task_count") and project.task_count is not None:
                project.task_count = (project.task_count or 0) + 1
                self.db.commit()
        except Exception:
            pass

    def _build_assignment_response(self, assignment: TaskAssignment) -> TaskAssignmentResponse:
        emp_name = emp_code = None
        if assignment.employee:
            emp_name = f"{assignment.employee.first_name} {assignment.employee.last_name}"
            emp_code = assignment.employee.employee_code
        return TaskAssignmentResponse(
            id=assignment.id,
            task_id=assignment.task_id,
            employee_id=assignment.employee_id,
            employee_name=emp_name,
            employee_code=emp_code,
            assigned_by=assignment.assigned_by,
            assigned_hours=float(assignment.assigned_hours or 0),
            planned_start_date=assignment.planned_start_date,
            planned_end_date=assignment.planned_end_date,
            actual_start_date=assignment.actual_start_date,
            actual_end_date=assignment.actual_end_date,
            status=assignment.status,
            assigned_at=assignment.assigned_at,
            completed_at=assignment.completed_at,
            notes=assignment.notes,
        )

    def _build_response(self, task: Task) -> TaskResponse:
        project_name = None
        if hasattr(task, "project") and task.project:
            project_name = (
                getattr(task.project, "project_name", None)
                or getattr(task.project, "name", None)
            )

        scope_name = None
        if hasattr(task, "scope") and task.scope:
            scope_name = (
                getattr(task.scope, "name", None)
                or getattr(task.scope, "scope_name", None)
            )

        assignments = []
        if task.assignments:
            for a in task.assignments:
                if a.status != "CANCELLED":
                    assignments.append(self._build_assignment_response(a))

        return TaskResponse(
            id=task.id,
            task_code=task.task_code,
            title=task.title,
            description=task.description,
            project_id=task.project_id,
            project_name=project_name,
            parent_task_id=task.parent_task_id,
            scope_of_work_id=task.scope_of_work_id,
            scope_name=scope_name,
            department_category=task.department_category,
            status=task.status,
            priority=task.priority,
            estimated_hours=float(task.estimated_hours or 0),
            actual_hours=float(task.actual_hours or 0),
            planned_start_date=task.planned_start_date,
            planned_end_date=task.planned_end_date,
            actual_start_date=task.actual_start_date,
            actual_end_date=task.actual_end_date,
            received_date=task.received_date,
            planned_delivery_date=task.planned_delivery_date,
            actual_delivery_date=task.actual_delivery_date,
            progress=float(task.progress or 0),
            remarks=task.remarks,
            is_active=task.is_active,
            assignments=assignments,
            created_at=task.created_at,
        )

    def _build_list_response(self, task: Task) -> TaskListResponse:
        project_name = None
        if hasattr(task, "project") and task.project:
            project_name = (
                getattr(task.project, "project_name", None)
                or getattr(task.project, "name", None)
            )

        active_assignments = [
            a for a in (task.assignments or []) if a.status != "CANCELLED"
        ]

        return TaskListResponse(
            id=task.id,
            task_code=task.task_code,
            title=task.title,
            project_id=task.project_id,
            project_name=project_name,
            department_category=task.department_category,
            status=task.status,
            priority=task.priority,
            estimated_hours=float(task.estimated_hours or 0),
            actual_hours=float(task.actual_hours or 0),
            progress=float(task.progress or 0),
            planned_start_date=task.planned_start_date,
            planned_end_date=task.planned_end_date,
            planned_delivery_date=task.planned_delivery_date,
            actual_delivery_date=task.actual_delivery_date,
            assignee_count=len(active_assignments),
        )
