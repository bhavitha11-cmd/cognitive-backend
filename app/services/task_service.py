import uuid
from datetime import date, datetime, timezone
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
from app.services.project_metrics_service import ProjectMetricsService


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
        user_context=None,
    ) -> tuple[list[TaskListResponse], int]:
        if user_context:
            tasks = self.repo.get_all_scoped(
                user_context,
                skip=skip, limit=limit, project_id=project_id,
                status=status, dept_cat=dept_cat, search=search,
            )
            total = self.repo.count_scoped(
                user_context,
                project_id=project_id, status=status,
                dept_cat=dept_cat, search=search,
            )
        else:
            tasks = self.repo.get_all(
                skip=skip, limit=limit, project_id=project_id,
                status=status, dept_cat=dept_cat, search=search,
            )
            total = self.repo.count(
                project_id=project_id, status=status,
                dept_cat=dept_cat, search=search,
            )
        return [self._build_list_response(t) for t in tasks], total

    def get_by_id(self, id: UUID, user_context=None) -> TaskResponse:
        task = self.repo.get_by_id(id, load_assignments=True)
        if not task:
            raise ValueError(f"Task with id {id} not found")
        # Enforce visibility check if user_context is provided
        if user_context and not self.repo.is_visible_to_user(id, user_context):
            raise ValueError("You do not have permission to view this task")
        return self._build_response(task)

    def get_by_project(self, project_id: UUID) -> list[TaskListResponse]:
        tasks = self.repo.get_tasks_by_project(project_id)
        return [self._build_list_response(t) for t in tasks]

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(self, data: TaskCreate, user_context=None) -> TaskResponse:
        # Validate project exists and is in an acceptable state
        project = self._get_project(data.project_id)
        if not project:
            raise ValueError(f"Project with id {data.project_id} not found")
        if hasattr(project, "status") and project.status not in ("Yet To Start", "In Progress", "YET TO START", "IN PROGRESS"):
            raise ValueError(
                f"Cannot add tasks to a project with status '{project.status}'. "
                "Project must be Yet To Start or In Progress."
            )

        # Resolve/Create team automatically if department_category is provided (acts as team)
        team_id = data.team_id
        dept_cat = data.department_category

        # Auto-set department_category from scope if scope provided and dept not set
        if data.scope_of_work_id:
            scope = self._get_scope(data.scope_of_work_id)
            if scope and not dept_cat and hasattr(scope, "department_category"):
                dept_cat = scope.department_category

        if dept_cat:
            from app.models.team import Team
            team = self.db.scalar(
                select(Team).where(
                    Team.department_id == project.department_id,
                    (Team.team_code == dept_cat) | (Team.team_name.ilike(f"%{dept_cat}%"))
                )
            )
            if not team:
                # Auto-create the team
                team = Team(
                    id=uuid.uuid4(),
                    team_code=dept_cat,
                    team_name=f"{dept_cat} Team",
                    department_id=project.department_id,
                    is_active=True
                )
                self.db.add(team)
                self.db.flush()
            team_id = team.id

        if not team_id:
            raise ValueError("Team could not be determined. Please specify a team or department category.")

        # Validate team exists and matches project's department
        from app.models.team import Team
        team = self.db.get(Team, team_id)
        if not team:
            raise ValueError("Selected team not found")
        if not team.is_active:
            raise ValueError("Cannot assign tasks to an inactive team")
        if team.department_id != project.department_id:
            raise ValueError("Selected team must belong to the same department as the project")

        # Validate task planned dates against project boundaries
        if data.planned_end_date and hasattr(project, "planned_end_date") and project.planned_end_date:
            if data.planned_end_date > project.planned_end_date:
                raise ValueError(
                    f"Task Planned End Date ({data.planned_end_date}) cannot be after "
                    f"the Project End Date ({project.planned_end_date})."
                )
        if data.planned_start_date and data.planned_end_date and data.planned_start_date > data.planned_end_date:
            raise ValueError("Task Planned Start Date cannot be after its Planned End Date.")

        # Enforce: only project members, PM, or admins can create tasks
        if user_context is not None:
            from app.core.rbac import DataAccessLevel
            if not (user_context.is_super_admin or user_context.data_access_level == DataAccessLevel.FULL):
                is_pm = (project.project_manager_id == user_context.employee_id)
                if not is_pm:
                    from app.models.project_member import ProjectMember
                    member = self.db.scalars(
                        select(ProjectMember).where(
                            ProjectMember.project_id == data.project_id,
                            ProjectMember.employee_id == user_context.employee_id,
                            ProjectMember.left_at.is_(None),
                        )
                    ).first()
                    if not member:
                        raise ValueError(
                            "You are not a member of this project. "
                            "Only project members, the project manager, or an admin can create tasks."
                        )

        # Validate task_code uniqueness within project
        existing = self.repo.get_by_code_and_project(data.task_code, data.project_id)
        if existing:
            raise ValueError(
                f"Task code '{data.task_code}' already exists in this project"
            )

        task_data = data.model_dump()
        assigned_employee_id = task_data.pop("assigned_employee_id", None)
        task_data["team_id"] = team_id
        task_data["department_category"] = dept_cat
        if self.current_user_id:
            task_data["created_by"] = self.current_user_id

        task = self.repo.create(task_data)

        # Create auto-assignment if assigned_employee_id is provided
        if assigned_employee_id:
            employee = self.db.get(Employee, assigned_employee_id)
            if not employee:
                raise ValueError(f"Employee with id {assigned_employee_id} not found")
            if not employee.is_active:
                raise ValueError("Cannot assign an inactive employee to a task")

            assignment_data = {
                "task_id": task.id,
                "employee_id": assigned_employee_id,
                "assigned_by": self.current_user_id,
                "assigned_hours": float(task.estimated_hours or 0),
                "planned_start_date": task.planned_start_date,
                "planned_end_date": task.planned_end_date,
                "notes": "Auto-assigned on task creation",
                "status": "ASSIGNED",
            }
            assignment = self.repo.create_assignment(assignment_data)

            # Trigger Task Continuity check for newly created assignment
            from app.services.task_continuity_service import TaskContinuityService
            continuity_svc = TaskContinuityService(self.db, self.current_user_id)
            continuity_svc.check_and_create_risk_for_assignment(assignment)

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

        # Recalculate project metrics (estimated_hours, progress, status, dates)
        self._trigger_project_recalc(task.project_id)

        return self._build_response(task)

    # ── Update ─────────────────────────────────────────────────────────────────

    def update(self, id: UUID, data: TaskUpdate) -> TaskResponse:
        task = self.repo.get_by_id(id, load_assignments=True)
        if not task:
            raise ValueError(f"Task with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)
        has_assignee_field = "assigned_employee_id" in update_data
        assigned_employee_id = update_data.pop("assigned_employee_id", None)

        # Resolve/Create team automatically if department_category is changed
        dept_cat = update_data.get("department_category")
        if dept_cat:
            from app.models.project import Project
            project = self.db.get(Project, task.project_id)
            if project:
                from app.models.team import Team
                team = self.db.scalar(
                    select(Team).where(
                        Team.department_id == project.department_id,
                        (Team.team_code == dept_cat) | (Team.team_name.ilike(f"%{dept_cat}%"))
                    )
                )
                if not team:
                    team = Team(
                        id=uuid.uuid4(),
                        team_code=dept_cat,
                        team_name=f"{dept_cat} Team",
                        department_id=project.department_id,
                        is_active=True
                    )
                    self.db.add(team)
                    self.db.flush()
                update_data["team_id"] = team.id

        # Validate team if changed
        if "team_id" in update_data and update_data["team_id"] != task.team_id:
            from app.models.team import Team
            team = self.db.get(Team, update_data["team_id"])
            if not team:
                raise ValueError("Selected team not found")
            if not team.is_active:
                raise ValueError("Cannot assign tasks to an inactive team")
            
            # Fetch task's project
            from app.models.project import Project
            project = self.db.get(Project, task.project_id)
            if project and team.department_id != project.department_id:
                raise ValueError("Selected team must belong to the same department as the project")

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

        # Handle assignee changes
        if has_assignee_field:
            active_assigns = [a for a in (task.assignments or []) if a.status != "CANCELLED"]
            current_emp_id = active_assigns[0].employee_id if active_assigns else None
            
            # If the assignee has changed
            if assigned_employee_id != current_emp_id:
                # Cancel existing active assignments
                for a in active_assigns:
                    self.repo.update_assignment(a, {"status": "CANCELLED"})
                
                # If a new employee is assigned, create assignment
                if assigned_employee_id:
                    employee = self.db.get(Employee, assigned_employee_id)
                    if not employee:
                        raise ValueError(f"Employee with id {assigned_employee_id} not found")
                    if not employee.is_active:
                        raise ValueError("Cannot assign an inactive employee to a task")
                    
                    assignment_data = {
                        "task_id": task.id,
                        "employee_id": assigned_employee_id,
                        "assigned_by": self.current_user_id,
                        "assigned_hours": float(task.estimated_hours or 0),
                        "planned_start_date": task.planned_start_date,
                        "planned_end_date": task.planned_end_date,
                        "notes": "Assigned on task update",
                        "status": "ASSIGNED",
                    }
                    assignment = self.repo.create_assignment(assignment_data)

                    # Trigger Task Continuity check for newly updated assignment
                    from app.services.task_continuity_service import TaskContinuityService
                    continuity_svc = TaskContinuityService(self.db, self.current_user_id)
                    continuity_svc.check_and_create_risk_for_assignment(assignment)

        AuditService.log(
            self.db, "task", id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=update_data,
        )

        task = self.repo.get_by_id(id, load_assignments=True)

        # Recalculate project metrics whenever task changes
        self._trigger_project_recalc(task.project_id)

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

        project_id = task.project_id  # capture before soft-delete

        self.repo.update(task, {"is_active": False})

        AuditService.log(
            self.db, "task", id, "DELETE",
            performed_by=self.current_user_id,
            old_value={"task_code": task.task_code, "status": task.status},
        )

        # Recalculate project metrics after task removal
        self._trigger_project_recalc(project_id)

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
            update_data["completed_at"] = datetime.now(timezone.utc)

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

    def _trigger_project_recalc(self, project_id: UUID) -> None:
        """Fire-and-forget project metrics recalculation. Non-blocking on error."""
        import logging
        try:
            ProjectMetricsService.recalculate(self.db, project_id)
            self.db.commit()
        except Exception:
            logging.getLogger(__name__).warning(
                "[TaskService] project_metrics recalc failed for project %s",
                project_id, exc_info=True,
            )
            self.db.rollback()

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

        team_name = team_code = None
        if hasattr(task, "team") and task.team:
            team_name = task.team.team_name
            team_code = task.team.team_code

        return TaskResponse(
            id=task.id,
            task_code=task.task_code,
            title=task.title,
            description=task.description,
            project_id=task.project_id,
            project_name=project_name,
            team_id=task.team_id,
            team_name=team_name,
            team_code=team_code,
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
            rework_count=task.rework_count or 0,
            total_rework_hours=float(task.total_rework_hours or 0),
            original_estimated_hours=float(task.original_estimated_hours or 0) if task.original_estimated_hours else None,
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

        assignments_response = []
        for a in active_assignments:
            assignments_response.append(self._build_assignment_response(a))

        team_name = team_code = None
        if hasattr(task, "team") and task.team:
            team_name = task.team.team_name
            team_code = task.team.team_code

        return TaskListResponse(
            id=task.id,
            task_code=task.task_code,
            title=task.title,
            project_id=task.project_id,
            project_name=project_name,
            team_id=task.team_id,
            team_name=team_name,
            team_code=team_code,
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
            rework_count=task.rework_count or 0,
            total_rework_hours=float(task.total_rework_hours or 0),
            assignee_count=len(active_assignments),
            assignments=assignments_response,
        )
