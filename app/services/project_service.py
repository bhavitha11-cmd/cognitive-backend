from uuid import UUID

from sqlalchemy import and_, func, select

from app.models.employee import Employee
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.audit_service import AuditService
from app.services.scheduling_service import SchedulingService



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
                     completed_task_count: int = 0) -> ProjectResponse:
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
            "part_number": project.project_code,
            "name": project.name,
            "part_name": project.part_name,
            "description": project.description,
            "client_id": project.client_id,
            "client_name": client_name,
            "project_manager_id": project.project_manager_id,
            "project_manager_name": pm_name,
            "status": project.status,
            "priority": project.priority,
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
            "status_reason": project.status_reason,
            "is_active": project.is_active,
            "task_count": task_count,
            "completed_task_count": completed_task_count,
            # Read from stored computed columns — never compute on-the-fly
            "actual_hours": float(project.actual_hours or 0),
            "progress": float(project.progress or 0),
            "created_at": project.created_at,
        }
        return ProjectResponse(**data)

    def _get_task_counts(self, project_id: UUID) -> tuple[int, int]:
        """Returns (total_tasks, completed_tasks)."""
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
            return total, completed
        except Exception:
            return 0, 0

    # ── public API ────────────────────────────────────────────────────────────

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        client_id: UUID | None = None,
        status: str | None = None,
        user_context=None,
    ) -> tuple[list[ProjectResponse], int]:
        if user_context:
            projects = self.repo.get_all_scoped(
                user_context, skip=skip, limit=limit, search=search, client_id=client_id, status=status
            )
            total = self.repo.count_scoped(
                user_context, search=search, client_id=client_id, status=status
            )
        else:
            projects = self.repo.get_all(
                skip=skip, limit=limit, search=search, client_id=client_id, status=status
            )
            total = self.repo.count(search=search, client_id=client_id, status=status)

        responses: list[ProjectResponse] = []
        for p in projects:
            tc, cc = self._get_task_counts(p.id)
            responses.append(self._to_response(p, task_count=tc, completed_task_count=cc))
        return responses, total

    def get_by_id(self, id: UUID, user_context=None) -> ProjectResponse:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")
        # Enforce visibility check if user_context is provided
        if user_context and not self.repo.is_visible_to_user(id, user_context):
            raise ValueError("You do not have permission to view this project")
        tc, cc = self._get_task_counts(id)
        return self._to_response(project, task_count=tc, completed_task_count=cc)

    def create(self, data: ProjectCreate) -> ProjectResponse:
        # Validate client exists and is active
        client = self._get_client(data.client_id)
        if not client:
            raise ValueError(f"Client with id {data.client_id} not found")
        if not getattr(client, "is_active", True):
            raise ValueError(f"Client with id {data.client_id} is not active")

        # Validate project_code (mapped from part_number) uniqueness
        if self.repo.get_by_code(data.part_number):
            raise ValueError(f"Project with Part Number '{data.part_number}' already exists")

        # Validate project_manager_id if provided
        if data.project_manager_id is not None:
            pm = self.db.get(Employee, data.project_manager_id)
            if not pm:
                raise ValueError(f"Employee (project manager) with id {data.project_manager_id} not found")

        # Live Scheduling Logic: Calculate planned_end_date and validate capacity
        planned_start = data.planned_start_date
        planned_end = data.planned_end_date
        est_hours = float(data.estimated_hours or 0.0)

        if planned_start and est_hours > 0 and not planned_end:
            planned_end = SchedulingService.calculate_end_date(planned_start, est_hours, self.db)

        if planned_start and planned_end:
            if planned_start > planned_end:
                raise ValueError("Planned start date cannot be after planned end date")
            capacity = SchedulingService.calculate_working_hours(planned_start, planned_end, self.db)
            if est_hours > capacity:
                raise ValueError("The selected date range does not provide enough working hours for the estimated effort.")

        payload = data.model_dump()
        payload["project_code"] = payload.pop("part_number")
        payload["planned_end_date"] = planned_end
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

        if "part_number" in update_data:
            update_data["project_code"] = update_data.pop("part_number")

        # Validate project_code uniqueness (excluding self)
        if "project_code" in update_data and update_data["project_code"] != project.project_code:
            existing = self.repo.get_by_code(update_data["project_code"])
            if existing and existing.id != id:
                raise ValueError(
                    f"Project with Part Number '{update_data['project_code']}' already exists"
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

        # Live Scheduling Logic: Calculate planned_end_date and validate capacity
        planned_start = update_data.get("planned_start_date", project.planned_start_date)
        planned_end = update_data.get("planned_end_date", project.planned_end_date)
        est_hours = update_data.get("estimated_hours", project.estimated_hours)
        if est_hours is None:
            est_hours = 0.0
        else:
            est_hours = float(est_hours)

        if planned_start and est_hours > 0 and not planned_end:
            planned_end = SchedulingService.calculate_end_date(planned_start, est_hours, self.db)
            update_data["planned_end_date"] = planned_end

        if planned_start and planned_end:
            if planned_start > planned_end:
                raise ValueError("Planned start date cannot be after planned end date")
            capacity = SchedulingService.calculate_working_hours(planned_start, planned_end, self.db)
            if est_hours > capacity:
                raise ValueError("The selected date range does not provide enough working hours for the estimated effort.")

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
            tc, cc = self._get_task_counts(id)
            return self._to_response(project, task_count=tc, completed_task_count=cc)
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

    def update_status(self, id: UUID, new_status: str, reason: str | None = None) -> ProjectResponse:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")

        update_data: dict = {"status": new_status}
        if reason is not None:
            update_data["status_reason"] = reason

        old_status = project.status
        try:
            project = self.repo.update(project, update_data)
            project = self.repo.get_by_id(project.id)
            AuditService.log(
                self.db,
                "project",
                id,
                "STATUS_CHANGE",
                performed_by=self.current_user_id,
                old_value={"status": old_status},
                new_value={"status": new_status, "status_reason": reason},
            )
            tc, cc = self._get_task_counts(id)
            return self._to_response(project, task_count=tc, completed_task_count=cc)
        except Exception:
            self.db.rollback()
            raise

    # ── Member management ──────────────────────────────────────────────────────

    def _is_pm_or_admin(self, project, user_context) -> bool:
        from app.core.rbac import DataAccessLevel
        if user_context is None:
            return False
        if user_context.is_super_admin or user_context.data_access_level == DataAccessLevel.FULL:
            return True
        return project.project_manager_id == user_context.employee_id

    def get_members(self, project_id: UUID) -> list:
        from app.schemas.project import ProjectMemberResponse
        project = self.repo.get_by_id(project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")
        members = self.repo.get_members(project_id)
        results = []
        for m in members:
            emp_name = emp_code = None
            if m.employee:
                emp_name = f"{m.employee.first_name} {m.employee.last_name}"
                emp_code = m.employee.employee_code
            results.append(ProjectMemberResponse(
                id=m.id,
                project_id=m.project_id,
                employee_id=m.employee_id,
                employee_name=emp_name,
                employee_code=emp_code,
                role=m.role,
                allocation_pct=m.allocation_pct,
                joined_at=m.joined_at,
            ))
        return results

    def add_member(self, project_id: UUID, employee_id: UUID, role: str, allocation_pct: int,
                   user_context=None):
        from app.schemas.project import ProjectMemberResponse
        project = self.repo.get_by_id(project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")

        if not self._is_pm_or_admin(project, user_context):
            raise PermissionError("Only the project manager or an admin can add members")

        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee with id {employee_id} not found")
        if not employee.is_active:
            raise ValueError("Cannot add an inactive employee as a project member")

        existing = self.repo.get_active_member(project_id, employee_id)
        if existing:
            raise ValueError("Employee is already an active member of this project")

        member = self.repo.add_member({
            "project_id": project_id,
            "employee_id": employee_id,
            "role": role,
            "allocation_pct": allocation_pct,
        })

        # Reload to get relationships
        member = self.repo.get_member_by_id(member.id)
        emp_name = emp_code = None
        if member.employee:
            emp_name = f"{member.employee.first_name} {member.employee.last_name}"
            emp_code = member.employee.employee_code

        AuditService.log(
            self.db, "project_member", member.id, "ADD_MEMBER",
            performed_by=self.current_user_id,
            new_value={"project_id": str(project_id), "employee_id": str(employee_id), "role": role},
        )

        return ProjectMemberResponse(
            id=member.id,
            project_id=member.project_id,
            employee_id=member.employee_id,
            employee_name=emp_name,
            employee_code=emp_code,
            role=member.role,
            allocation_pct=member.allocation_pct,
            joined_at=member.joined_at,
        )

    def remove_member(self, project_id: UUID, member_id: UUID, user_context=None) -> None:
        project = self.repo.get_by_id(project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")

        if not self._is_pm_or_admin(project, user_context):
            raise PermissionError("Only the project manager or an admin can remove members")

        member = self.repo.get_member_by_id(member_id)
        if not member or member.project_id != project_id:
            raise ValueError(f"Member with id {member_id} not found in this project")
        if member.left_at is not None:
            raise ValueError("Member has already been removed from this project")

        self.repo.remove_member(member)

        AuditService.log(
            self.db, "project_member", member_id, "REMOVE_MEMBER",
            performed_by=self.current_user_id,
            old_value={"project_id": str(project_id), "employee_id": str(member.employee_id)},
        )

    def get_project_stats(self, id: UUID) -> dict:
        project = self.repo.get_by_id(id)
        if not project:
            raise ValueError(f"Project with id {id} not found")

        tc, cc = self._get_task_counts(id)

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
        actual_hours = float(project.actual_hours or 0)
        contract = float(project.contract_hours) if project.contract_hours is not None else None
        hours_remaining = max(0.0, estimated - actual_hours) if estimated else None

        return {
            "project_id": str(id),
            "project_code": project.project_code,
            "part_number": project.project_code,
            "name": project.name,
            "status": project.status,
            "task_count": tc,
            "completed_task_count": cc,
            "pending_task_count": tc - cc,
            "completion_pct": round(float(project.progress or 0), 1),
            "member_count": member_count,
            "estimated_hours": estimated,
            "contract_hours": contract,
            "actual_hours": actual_hours,
            "hours_remaining": hours_remaining,
        }

    def recalculate_all(self) -> dict:
        """Admin backfill: recalculate metrics for every active project."""
        import logging
        from app.services.project_metrics_service import ProjectMetricsService

        projects = self.db.scalars(
            select(Project).where(Project.is_active == True)  # noqa: E712
        ).all()

        results: dict = {"total": len(projects), "updated": 0, "errors": []}
        for project in projects:
            try:
                ProjectMetricsService.recalculate(self.db, project.id)
                self.db.commit()
                results["updated"] += 1
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "[ProjectService] recalculate_all failed for project %s: %s",
                    project.id, exc,
                )
                results["errors"].append({"project_id": str(project.id), "error": str(exc)})
        return results
