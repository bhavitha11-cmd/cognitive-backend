import uuid
from collections import deque
from datetime import date, timedelta, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.employee_schedule import EmployeeSchedule
from app.models.task_dependency import TaskDependency
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.schemas.planning import (
    EmployeeScheduleCreate, EmployeeScheduleUpdate,
    TaskDependencyCreate, EmployeeCapacityResponse, CapacityWeek,
    GanttResponse, GanttTask, GanttDependency,
    EmployeeScheduleResponse, TaskDependencyResponse,
)
from app.services.audit_service import AuditService
from app.services.working_day_engine import WorkingDayEngine


class PlanningService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Employee Schedule CRUD ───────────────────────────────────────────

    def create_schedule(self, data: EmployeeScheduleCreate) -> EmployeeScheduleResponse:
        existing = self.db.scalar(
            select(EmployeeSchedule).where(
                EmployeeSchedule.employee_id == data.employee_id,
                EmployeeSchedule.week_start_date == data.week_start_date,
            )
        )
        if existing:
            raise HTTPException(400, "Schedule already exists for this employee and week")
        schedule = EmployeeSchedule(**data.model_dump())
        self.db.add(schedule); self.db.commit(); self.db.refresh(schedule)
        AuditService.log(self.db, "EmployeeSchedule", schedule.id, "CREATE", performed_by=self.current_user_id)
        return self._schedule_to_response(schedule)

    def update_schedule(self, id: uuid.UUID, data: EmployeeScheduleUpdate) -> EmployeeScheduleResponse:
        schedule = self.db.get(EmployeeSchedule, id)
        if not schedule:
            raise HTTPException(404, "Schedule not found")
        update_data = data.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(schedule, k, v)
        self.db.commit(); self.db.refresh(schedule)
        AuditService.log(self.db, "EmployeeSchedule", schedule.id, "UPDATE", performed_by=self.current_user_id)
        return self._schedule_to_response(schedule)

    def get_employee_schedules(self, employee_id: uuid.UUID, from_date: date, to_date: date) -> list[EmployeeScheduleResponse]:
        schedules = self.db.scalars(
            select(EmployeeSchedule)
            .where(EmployeeSchedule.employee_id == employee_id)
            .where(EmployeeSchedule.week_start_date >= from_date)
            .where(EmployeeSchedule.week_start_date <= to_date)
            .order_by(EmployeeSchedule.week_start_date)
        ).all()
        return [self._schedule_to_response(s) for s in schedules]

    def _schedule_to_response(self, s: EmployeeSchedule) -> EmployeeScheduleResponse:
        return EmployeeScheduleResponse(
            id=s.id,
            employee_id=s.employee_id,
            employee_name=f"{s.employee.first_name} {s.employee.last_name}" if s.employee else None,
            employee_code=s.employee.employee_code if s.employee else None,
            week_start_date=s.week_start_date,
            available_hours=float(s.available_hours),
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    # ── Employee Capacity ─────────────────────────────────────────────────

    def get_employee_capacity(self, employee_id: uuid.UUID, from_date: date, to_date: date) -> EmployeeCapacityResponse:
        from app.models.employee import Employee
        emp = self.db.get(Employee, employee_id)
        if not emp:
            raise HTTPException(404, "Employee not found")
        emp_name = f"{emp.first_name} {emp.last_name}"

        schedules = self.db.scalars(
            select(EmployeeSchedule)
            .where(EmployeeSchedule.employee_id == employee_id)
            .where(EmployeeSchedule.week_start_date >= from_date)
            .where(EmployeeSchedule.week_start_date <= to_date)
            .order_by(EmployeeSchedule.week_start_date)
        ).all()
        schedule_map = {s.week_start_date: float(s.available_hours) for s in schedules}

        assignments = self.db.execute(
            select(
                TaskAssignment.planned_start_date,
                TaskAssignment.planned_end_date,
                TaskAssignment.assigned_hours,
            )
            .where(TaskAssignment.employee_id == employee_id)
            .where(
                (TaskAssignment.planned_start_date <= to_date) &
                (TaskAssignment.planned_end_date >= from_date)
            )
        ).all()

        weeks: list[CapacityWeek] = []
        current = from_date
        while current <= to_date:
            monday = current - timedelta(days=current.weekday())
            avail = schedule_map.get(monday, 40.0)

            week_end = monday + timedelta(days=6)
            scheduled = 0.0
            for a in assignments:
                a_start = a.planned_start_date or monday
                a_end = a.planned_end_date or week_end
                overlap_start = max(a_start, monday)
                overlap_end = min(a_end, week_end)
                if overlap_start <= overlap_end:
                    total_days = (a_end - a_start).days + 1
                    overlap_days = (overlap_end - overlap_start).days + 1
                    if total_days > 0:
                        scheduled += float(a.assigned_hours) * (overlap_days / total_days)

            utilization = round((scheduled / avail * 100) if avail > 0 else 0, 1)
            weeks.append(CapacityWeek(
                week_start_date=monday,
                available_hours=round(avail, 2),
                scheduled_hours=round(scheduled, 2),
                utilization_pct=utilization,
            ))
            current += timedelta(days=7)

        return EmployeeCapacityResponse(
            employee_id=employee_id,
            employee_name=emp_name,
            weeks=weeks,
        )

    # ── Task Dependencies CRUD ────────────────────────────────────────────

    def create_dependency(self, data: TaskDependencyCreate) -> TaskDependencyResponse:
        task = self.db.get(Task, data.task_id)
        if not task:
            raise HTTPException(404, f"Task {data.task_id} not found")
        dep = self.db.get(Task, data.depends_on_task_id)
        if not dep:
            raise HTTPException(404, f"Dependency task {data.depends_on_task_id} not found")
        if data.task_id == data.depends_on_task_id:
            raise HTTPException(400, "Task cannot depend on itself")
        existing = self.db.scalar(
            select(TaskDependency).where(
                TaskDependency.task_id == data.task_id,
                TaskDependency.depends_on_task_id == data.depends_on_task_id,
            )
        )
        if existing:
            raise HTTPException(400, "Dependency already exists")
        dependency = TaskDependency(**data.model_dump())
        self.db.add(dependency); self.db.commit(); self.db.refresh(dependency)
        AuditService.log(self.db, "TaskDependency", dependency.id, "CREATE", performed_by=self.current_user_id)
        return self._dep_to_response(dependency)

    def delete_dependency(self, id: uuid.UUID) -> None:
        dep = self.db.get(TaskDependency, id)
        if not dep:
            raise HTTPException(404, "Dependency not found")
        self.db.delete(dep); self.db.commit()
        AuditService.log(self.db, "TaskDependency", id, "DELETE", performed_by=self.current_user_id)

    def get_task_dependencies(self, task_id: uuid.UUID) -> list[TaskDependencyResponse]:
        deps = self.db.scalars(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        ).all()
        return [self._dep_to_response(d) for d in deps]

    def get_project_dependencies(self, project_id: uuid.UUID) -> list[TaskDependencyResponse]:
        deps = self.db.execute(
            select(TaskDependency)
            .join(Task, Task.id == TaskDependency.task_id)
            .where(Task.project_id == project_id)
        ).scalars().all()
        return [self._dep_to_response(d) for d in deps]

    def _dep_to_response(self, d: TaskDependency) -> TaskDependencyResponse:
        return TaskDependencyResponse(
            id=d.id,
            task_id=d.task_id,
            depends_on_task_id=d.depends_on_task_id,
            task_code=d.task.task_code if d.task else None,
            task_title=d.task.title if d.task else None,
            depends_on_task_code=d.depends_on.task_code if d.depends_on else None,
            depends_on_task_title=d.depends_on.title if d.depends_on else None,
            dependency_type=d.dependency_type,
            created_at=d.created_at,
        )

    # ── Gantt Data ────────────────────────────────────────────────────────

    def get_gantt_data(self, project_id: uuid.UUID) -> GanttResponse:
        tasks = self.db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.is_active == True)
            .order_by(Task.scheduled_start_date, Task.task_code)
        ).all()

        task_ids = [t.id for t in tasks]

        assignments = self.db.execute(
            select(TaskAssignment).where(TaskAssignment.task_id.in_(task_ids))
        ).scalars().all()
        assignment_map: dict[uuid.UUID, list[dict]] = {}
        for a in assignments:
            assignment_map.setdefault(a.task_id, []).append({
                "employee_id": str(a.employee_id) if a.employee_id else None,
                "employee_name": f"{a.employee.first_name} {a.employee.last_name}" if a.employee else None,
                "assigned_hours": float(a.assigned_hours),
            })

        deps = self.db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
        ).scalars().all()

        gantt_tasks = []
        for t in tasks:
            gantt_tasks.append(GanttTask(
                id=t.id,
                task_code=t.task_code,
                title=t.title,
                scheduled_start_date=t.scheduled_start_date,
                scheduled_end_date=t.scheduled_end_date,
                planned_start_date=t.planned_start_date,
                planned_end_date=t.planned_end_date,
                actual_start_date=t.actual_start_date,
                actual_end_date=t.actual_end_date,
                progress=float(t.progress),
                estimated_hours=float(t.estimated_hours),
                actual_hours=float(t.actual_hours),
                status=t.status,
                priority=t.priority,
                assignees=assignment_map.get(t.id, []),
                project_id=t.project_id,
            ))

        gantt_deps = []
        for d in deps:
            gantt_deps.append(GanttDependency(
                id=d.id,
                task_id=d.task_id,
                depends_on_task_id=d.depends_on_task_id,
                dependency_type=d.dependency_type,
            ))

        return GanttResponse(tasks=gantt_tasks, dependencies=gantt_deps)

    # ── Auto-Schedule ─────────────────────────────────────────────────────

    def schedule_project(self, project_id: uuid.UUID) -> GanttResponse:
        tasks = self.db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.is_active == True)
            .order_by(Task.created_at)
        ).all()
        if not tasks:
            raise HTTPException(400, "No tasks found in project")

        deps = self.db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_([t.id for t in tasks]))
        ).all()

        task_dict = {t.id: t for t in tasks}
        in_degree: dict[uuid.UUID, int] = {t.id: 0 for t in tasks}
        dependents: dict[uuid.UUID, list[uuid.UUID]] = {t.id: [] for t in tasks}
        for d in deps:
            if d.depends_on_task_id in task_dict:
                dependents.setdefault(d.depends_on_task_id, []).append(d.task_id)
                in_degree[d.task_id] = in_degree.get(d.task_id, 0) + 1

        queue = deque(t_id for t_id, deg in in_degree.items() if deg == 0)
        sorted_tasks = []
        while queue:
            t_id = queue.popleft()
            sorted_tasks.append(task_dict[t_id])
            for dep_id in dependents.get(t_id, []):
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        for t in tasks:
            if t not in sorted_tasks:
                sorted_tasks.append(t)

        project_start = date.today()
        for t in tasks:
            if t.planned_start_date:
                project_start = min(project_start, t.planned_start_date)

        earliest_finish: dict[uuid.UUID, date] = {}
        for t in sorted_tasks:
            dep_dates = []
            for d in deps:
                if d.task_id == t.id and d.depends_on_task_id in earliest_finish:
                    dep_dates.append(earliest_finish[d.depends_on_task_id])

            est_start = max(project_start, max(dep_dates) if dep_dates else project_start)

            remaining = max(0, float(t.estimated_hours) - float(t.actual_hours))
            duration_days = max(1, round(remaining / 8))

            est_end = WorkingDayEngine.add_working_days(est_start, duration_days, self.db)

            t.scheduled_start_date = est_start
            t.scheduled_end_date = est_end
            earliest_finish[t.id] = est_end

        self.db.commit()

        for t in sorted_tasks:
            self.db.refresh(t)
        return self.get_gantt_data(project_id)

    # ── Employee Load Chart ────────────────────────────────────────────────

    def get_employee_load_chart(
        self,
        requesting_employee_id: uuid.UUID,
        from_date: date,
        to_date: date,
        department_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """
        Returns a hierarchical list of employees with their active task assignments
        formatted for a Gantt load chart. Respects reporting hierarchy visibility.
        """
        from app.models.employee import Employee
        from app.models.task import Task
        from app.models.project import Project
        from app.services.organization_hierarchy_service import OrganizationHierarchyService

        # Resolve visible employee IDs based on hierarchy
        hier_svc = OrganizationHierarchyService(self.db)
        visible_ids = hier_svc.get_visible_employee_ids(requesting_employee_id)

        # Load visible employees with their details
        emp_query = (
            select(Employee)
            .where(Employee.id.in_(visible_ids))
            .where(Employee.is_active == True)
        )
        if department_id:
            emp_query = emp_query.where(Employee.department_id == department_id)

        employees = self.db.scalars(emp_query).all()

        if team_id:
            from app.models.team_member import TeamMember
            team_emp_ids = set(
                row[0]
                for row in self.db.execute(
                    select(TeamMember.employee_id).where(TeamMember.team_id == team_id)
                ).all()
            )
            employees = [e for e in employees if e.id in team_emp_ids]

        emp_ids = [e.id for e in employees]
        if not emp_ids:
            return []

        # Load all active assignments overlapping the date range
        assignments = self.db.execute(
            select(TaskAssignment, Task, Project)
            .join(Task, Task.id == TaskAssignment.task_id)
            .join(Project, Project.id == Task.project_id)
            .where(TaskAssignment.employee_id.in_(emp_ids))
            .where(Task.is_active == True)
            .where(TaskAssignment.status != "CANCELLED")
            .where(
                (TaskAssignment.planned_end_date >= from_date) |
                (Task.planned_end_date >= from_date) |
                (Task.scheduled_end_date >= from_date)
            )
        ).all()

        # Group assignments by employee id
        emp_assignments: dict[uuid.UUID, list[dict]] = {e.id: [] for e in employees}
        for assignment, task, project in assignments:
            emp_id = assignment.employee_id
            if emp_id not in emp_assignments:
                continue
            start = (
                assignment.planned_start_date
                or task.planned_start_date
                or task.scheduled_start_date
            )
            end = (
                assignment.planned_end_date
                or task.planned_end_date
                or task.scheduled_end_date
            )
            emp_assignments[emp_id].append({
                "task_id": str(task.id),
                "task_code": task.task_code,
                "task_title": task.title,
                "project_id": str(project.id),
                "project_name": project.name,
                "status": task.status,
                "priority": task.priority,
                "progress": float(task.progress),
                "assigned_hours": float(assignment.assigned_hours),
                "estimated_hours": float(task.estimated_hours),
                "actual_hours": float(task.actual_hours),
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
            })

        # Build result rows
        emp_map = {e.id: e for e in employees}
        rows = []
        for emp_id in emp_ids:
            emp = emp_map.get(emp_id)
            if not emp:
                continue
            tasks_list = emp_assignments.get(emp_id, [])
            # "loaded until" = max end_date across active assignments
            end_dates = [
                t["end_date"] for t in tasks_list
                if t["end_date"] and t["status"] not in ("COMPLETED", "CANCELLED")
            ]
            loaded_until = max(end_dates) if end_dates else None

            # Compute load_status based on task count and hours
            active_tasks = [t for t in tasks_list if t["status"] not in ("COMPLETED", "CANCELLED")]
            total_assigned = sum(t["assigned_hours"] for t in active_tasks)
            if total_assigned == 0:
                load_status = "AVAILABLE"
            elif total_assigned > 48:
                load_status = "OVERLOADED"
            elif total_assigned >= 32:
                load_status = "OPTIMAL"
            else:
                load_status = "UNDERLOADED"

            # Hierarchy info
            parent_id = hier_svc._ensure_cache() or None
            mgr_id = hier_svc.cache.get_parent(emp_id)

            rows.append({
                "employee_id": str(emp_id),
                "employee_code": emp.employee_code,
                "employee_name": f"{emp.first_name} {emp.last_name}",
                "display_name": emp.display_name or f"{emp.first_name} {emp.last_name}",
                "profile_photo_url": emp.profile_photo_url,
                "designation": emp.designation.name if emp.designation else None,
                "department": emp.department.name if emp.department else None,
                "reporting_manager_id": str(mgr_id) if mgr_id else None,
                "loaded_until": loaded_until,
                "load_status": load_status,
                "total_assigned_hours": round(total_assigned, 2),
                "active_task_count": len(active_tasks),
                "tasks": tasks_list,
            })

        return rows
