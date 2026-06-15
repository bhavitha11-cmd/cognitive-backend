from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.employee import Employee
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.audit_service import AuditService


class ProjectService:
    def __init__(self, db, current_user_id: UUID | None = None):
        self.db = db
        self.repo = ProjectRepository(db)
        self.current_user_id = current_user_id

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_client(self, client_id: UUID):
        from app.models.client import Client
        return self.db.get(Client, client_id)

    def _to_response(self, project: Project, task_count: int = 0,
                     completed_task_count: int = 0, actual_hours: float = 0.0) -> ProjectResponse:
        client_name: str | None = None
        if project.client:
            client_name = getattr(project.client, "name", None) or getattr(
                project.client, "client_name", None
            )

        pm_name: str | None = None
        if project.project_manager:
            pm = project.project_manager
            pm_name = f"{pm.first_name} {pm.last_name}"

        data = {
            "id": project.id,
            "project_code": project.project_code,
            "name": project.name,
            "description": project.description,
            "client_id": project.client_id,
            "client_name": client_name,
            "project_manager_id": project.project_manager_id,
            "project_manager_name": pm_name,
            "status": project.status,
            "priority": project.priority,
            "billing_type": project.billing_type,
            "is_billable": project.is_billable,
            "planned_start_date": project.planned_start_date,
            "planned_end_date": project.planned_end_date,
            "actual_start_date": project.actual_start_date,
            "actual_end_date": project.actual_end_date,
            "estimated_hours": float(project.estimated_hours or 0),
            "contract_hours": float(project.contract_hours) if project.contract_hours is not None else None,
            "invoice_status": project.invoice_status,
            "tok_form": project.tok_form,
            "feedback_status": project.feedback_status,
            "is_active": project.is_active,
            "task_count": task_count,
            "completed_task_count": completed_task_count,
            "actual_hours": actual_hours,
            "created_at": project.created_at,
        }
        return ProjectResponse(**data)

    def _get_task_counts(self, project_id: UUID) -> tuple[int, int, float]:
        """Returns (total_tasks, completed_tasks, actual_hours)."""
        try:
            from app.models.task import Task
            total = self.db.scalar(
                select(func.count(Task.id)).where(
                    and_(Task.project_id == project_id, Task.is_active == True)  # noqa: E712
                )
            ) or 0
            completed = self.db.scalar(
                select(func.count(Task.id)).where(
                    and_(
                        Task.project_id == project_id,
                        Task.status == "COMPLETED",
                        Task.is_active == True,  # noqa: E712
                    )
                )
            ) or 0
            actual_hours_raw = self.db.scalar(
                select(func.coalesce(func.sum(Task.actual_hours), 0)).where(
                    and_(Task.project_id == project_id, Task.is_active == True)  # noqa: E712
                )
            ) or 0
            return total, completed, float(actual_hours_raw)
        except Exception:
            # Task model may not exist yet; return zeros gracefully
            return 0, 0, 0.0

    # ── public API ────────────────────────────────────────────────────────────

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[ProjectResponse], int]:
        projects = self.repo.get_all(
            skip=skip, limit=limit, search=search, client_id=client_id, status=status
        )
        total = self.repo.count(search=search, client_id=client_id, status=status)

        responses: list[ProjectResponse] = []
        for p in projects:
            tc, cc, ah = self._get_task_counts(p.id)
            responses.append(self._to_response(p, task_count=tc, completed_task_count=cc, actual_hours=ah))
        return responses, total

    def get_by_id(self, id: UUID) -> ProjectResponse:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")
        tc, cc, ah = self._get_task_counts(id)
        return self._to_response(project, task_count=tc, completed_task_count=cc, actual_hours=ah)

    def create(self, data: ProjectCreate) -> ProjectResponse:
        # Validate client exists and is active
        client = self._get_client(data.client_id)
        if not client:
            raise ValueError(f"Client with id {data.client_id} not found")
        if not getattr(client, "is_active", True):
            raise ValueError(f"Client with id {data.client_id} is not active")

        # Validate project_code uniqueness
        if self.repo.get_by_code(data.project_code):
            raise ValueError(f"Project with code '{data.project_code}' already exists")

        # Validate project_manager_id if provided
        if data.project_manager_id is not None:
            pm = self.db.get(Employee, data.project_manager_id)
            if not pm:
                raise ValueError(f"Employee (project manager) with id {data.project_manager_id} not found")

        payload = data.model_dump()
        payload["created_by"] = self.current_user_id

        try:
            project = self.repo.create(payload)
            # Reload with joins
            project = self.repo.get_by_id(project.id)
            AuditService.log(
                self.db,
                "project",
                project.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={
                    "project_code": project.project_code,
                    "name": project.name,
                    "client_id": str(project.client_id),
                    "status": project.status,
                },
            )
            return self._to_response(project)
        except Exception:
            self.db.rollback()
            raise

    def update(self, id: UUID, data: ProjectUpdate) -> ProjectResponse:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")

        update_data = data.model_dump(exclude_unset=True)

        # Validate project_code uniqueness (excluding self)
        if "project_code" in update_data and update_data["project_code"] != project.project_code:
            existing = self.repo.get_by_code(update_data["project_code"])
            if existing and existing.id != id:
                raise ValueError(
                    f"Project with code '{update_data['project_code']}' already exists"
                )

        # Validate client if changed
        if "client_id" in update_data:
            client = self._get_client(update_data["client_id"])
            if not client:
                raise ValueError(f"Client with id {update_data['client_id']} not found")
            if not getattr(client, "is_active", True):
                raise ValueError(f"Client with id {update_data['client_id']} is not active")

        # Validate project_manager if provided
        if "project_manager_id" in update_data and update_data["project_manager_id"] is not None:
            pm = self.db.get(Employee, update_data["project_manager_id"])
            if not pm:
                raise ValueError(
                    f"Employee (project manager) with id {update_data['project_manager_id']} not found"
                )

        old_values = {k: getattr(project, k, None) for k in update_data}

        try:
            project = self.repo.update(project, update_data)
            project = self.repo.get_by_id(project.id)
            AuditService.log(
                self.db,
                "project",
                id,
                "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
            tc, cc, ah = self._get_task_counts(id)
            return self._to_response(project, task_count=tc, completed_task_count=cc, actual_hours=ah)
        except Exception:
            self.db.rollback()
            raise

    def delete(self, id: UUID) -> None:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")

        # Block delete if active tasks exist
        try:
            from app.models.task import Task
            blocking_count = self.db.scalar(
                select(func.count(Task.id)).where(
                    and_(
                        Task.project_id == id,
                        Task.status.in_(["IN_PROGRESS", "NOT_STARTED"]),
                        Task.is_active == True,  # noqa: E712
                    )
                )
            ) or 0
            if blocking_count:
                raise ValueError(
                    f"Cannot delete project '{project.name}': {blocking_count} active task(s) "
                    f"in IN_PROGRESS or NOT_STARTED state. Complete or cancel them first."
                )
        except ImportError:
            pass

        try:
            AuditService.log(
                self.db,
                "project",
                id,
                "DELETE",
                performed_by=self.current_user_id,
                old_value={
                    "project_code": project.project_code,
                    "name": project.name,
                    "status": project.status,
                },
            )
            self.repo.delete_soft(project)
        except Exception:
            self.db.rollback()
            raise

    def get_project_stats(self, id: UUID) -> dict:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")

        tc, cc, ah = self._get_task_counts(id)

        member_count = 0
        try:
            from app.models.project_member import ProjectMember
            member_count = self.db.scalar(
                select(func.count(ProjectMember.id)).where(
                    and_(
                        ProjectMember.project_id == id,
                        ProjectMember.left_at.is_(None),
                    )
                )
            ) or 0
        except Exception:
            pass

        estimated = float(project.estimated_hours or 0)
        contract = float(project.contract_hours) if project.contract_hours is not None else None
        hours_remaining = max(0.0, estimated - ah) if estimated else None

        return {
            "project_id": str(id),
            "project_code": project.project_code,
            "name": project.name,
            "status": project.status,
            "task_count": tc,
            "completed_task_count": cc,
            "pending_task_count": tc - cc,
            "completion_pct": round((cc / tc * 100), 1) if tc else 0.0,
            "member_count": member_count,
            "estimated_hours": estimated,
            "contract_hours": contract,
            "actual_hours": ah,
            "hours_remaining": hours_remaining,
        }
