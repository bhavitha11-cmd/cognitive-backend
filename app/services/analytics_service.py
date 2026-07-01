import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, func, and_, case
from sqlalchemy.orm import Session, joinedload
from app.models.client import Client
from app.models.project import Project
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.time_entry import TimeEntry
from app.models.employee import Employee
from app.models.department import Department
from app.models.attendance import Attendance
from app.schemas.analytics import (
    DashboardStats, PlanVsActualProject, PlanVsActualResponse,
    EmployeeUtilization, UtilizationResponse, DepartmentLoad, DepartmentLoadResponse,
    OverdueTask, ClientPerformance, ClientPerformanceResponse,
    ScopeDistribution, ScopeDistributionResponse,
    SessionAnalytics, SessionAnalyticsResponse,
    ReworkAnalytics, ReworkAnalyticsResponse,
)
from app.models.task_work_session import TaskWorkSession
from app.models.employee_break import EmployeeBreak
from app.models.task_rework_history import TaskReworkHistory


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_stats(self, current_user_id: uuid.UUID | None = None) -> DashboardStats:
        from app.core.rbac import DataAccessLevel
        from app.services.dashboard.dashboard_common_service import DashboardCommonService

        now = datetime.now(timezone.utc)
        today = now.date()

        # Resolve scoped employee/project IDs for RBAC
        user_ctx = None
        if current_user_id is not None:
            from app.core.rbac import get_user_context
            user_ctx = get_user_context(self.db, str(current_user_id))

        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        # Scoped project IDs for TEAM/SELF access
        scoped_project_ids = None
        if user_ctx and user_ctx.data_access_level in (DataAccessLevel.TEAM, DataAccessLevel.SELF):
            from app.models.task_assignment import TaskAssignment as TA
            assigned_project_ids = self.db.scalars(
                select(Task.project_id)
                .join(TA, TA.task_id == Task.id)
                .where(TA.employee_id == user_ctx.employee_id)
                .distinct()
            ).all()
            scoped_project_ids = list(assigned_project_ids) if assigned_project_ids else []

        # FIX 6: total_clients = ALL clients; active_clients = only active
        total_clients = self.db.scalar(select(func.count(Client.id))) or 0
        active_clients = self.db.scalar(select(func.count(Client.id)).where(Client.is_active == True)) or 0

        # Project counts — scoped for TEAM/SELF
        proj_stmt_base = select(func.count(Project.id)).where(Project.is_active == True)
        if scoped_project_ids is not None:
            proj_stmt_base = select(func.count(Project.id)).where(
                Project.is_active == True, Project.id.in_(scoped_project_ids)
            )

        total_projects = self.db.scalar(proj_stmt_base) or 0
        active_projects_stmt = select(func.count(Project.id)).where(Project.is_active == True, Project.status.in_(["In Progress", "On Hold"]))
        completed_projects_stmt = select(func.count(Project.id)).where(Project.status == "Completed")
        if scoped_project_ids is not None:
            active_projects_stmt = active_projects_stmt.where(Project.id.in_(scoped_project_ids))
            completed_projects_stmt = completed_projects_stmt.where(Project.id.in_(scoped_project_ids))
        active_projects = self.db.scalar(active_projects_stmt) or 0
        completed_projects = self.db.scalar(completed_projects_stmt) or 0

        # Task counts
        total_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.is_active == True)) or 0
        pending_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.status == "NOT_STARTED", Task.is_active == True)) or 0
        in_progress_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.status == "IN_PROGRESS", Task.is_active == True)) or 0
        completed_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.status == "COMPLETED", Task.is_active == True)) or 0
        overdue_tasks = self.db.scalar(
            select(func.count(Task.id)).where(
                Task.planned_delivery_date < today,
                Task.status.not_in(["COMPLETED", "CANCELLED"]),
                Task.is_active == True,
            )
        ) or 0

        # Employee counts — scoped for TEAM/SELF
        emp_stmt = select(func.count(Employee.id)).where(Employee.is_active == True)
        if scoped_employee_ids is not None:
            emp_stmt = select(func.count(Employee.id)).where(
                Employee.is_active == True, Employee.id.in_(scoped_employee_ids)
            )
        total_employees = self.db.scalar(emp_stmt) or 0

        present_today = self.db.scalar(
            select(func.count(Attendance.id)).where(Attendance.date == today, Attendance.status == "PRESENT")
        ) or 0

        est = self.db.scalar(select(func.coalesce(func.sum(Project.estimated_hours), 0))) or 0
        act = self.db.scalar(
            select(func.coalesce(func.sum(TimeEntry.hours_spent), 0)).where(TimeEntry.status != "REJECTED")
        ) or 0

        est_f = float(est)
        act_f = float(act)
        overrun = round(((act_f - est_f) / est_f * 100) if est_f > 0 else 0, 1)

        return DashboardStats(
            total_clients=total_clients,
            active_clients=active_clients,
            total_projects=total_projects,
            active_projects=active_projects,
            completed_projects=completed_projects,
            total_tasks=total_tasks,
            pending_tasks=pending_tasks,
            in_progress_tasks=in_progress_tasks,
            completed_tasks=completed_tasks,
            overdue_tasks=overdue_tasks,
            total_employees=total_employees,
            active_employees=total_employees,
            present_today=present_today,
            total_estimated_hours=est_f,
            total_actual_hours=act_f,
            overrun_percentage=overrun,
        )

    def get_plan_vs_actual(self) -> PlanVsActualResponse:
        projects = self.db.scalars(
            select(Project).where(Project.is_active == True).order_by(Project.estimated_hours.desc())
        ).all()

        # FIX 4: Batch pre-fetch actual hours and task counts (no N+1)
        hours_result = self.db.execute(
            select(TimeEntry.project_id, func.sum(TimeEntry.hours_spent))
            .where(TimeEntry.status == "APPROVED")
            .group_by(TimeEntry.project_id)
        ).all()
        hours_by_project = {str(row[0]): float(row[1] or 0) for row in hours_result}

        task_counts_result = self.db.execute(
            select(
                Task.project_id,
                func.count(Task.id).label("total"),
                func.count(case((Task.status == "COMPLETED", 1))).label("completed")
            )
            .group_by(Task.project_id)
        ).all()
        task_data = {str(row[0]): {"total": row[1], "completed": row[2]} for row in task_counts_result}

        result = []
        total_est = 0.0
        total_act = 0.0

        for p in projects:
            est = float(p.estimated_hours or 0)
            actual = hours_by_project.get(str(p.id), 0.0)
            total_est += est
            total_act += actual

            td = task_data.get(str(p.id), {"total": 0, "completed": 0})
            task_count = td["total"]
            completed = td["completed"]

            result.append(PlanVsActualProject(
                id=p.id,
                part_number=p.project_code,
                name=p.name,
                client_name=p.client.name if p.client else None,
                status=p.status,
                estimated_hours=est,
                actual_hours=actual,
                overrun_hours=round(actual - est, 2),
                overrun_percentage=round(((actual - est) / est * 100) if est > 0 else 0, 1),
                task_count=task_count,
                completed_task_count=completed,
                planned_end_date=p.planned_end_date,
            ))

        overall_overrun = round(((total_act - total_est) / total_est * 100) if total_est > 0 else 0, 1)
        return PlanVsActualResponse(
            projects=result, total_estimated=total_est,
            total_actual=total_act, total_overrun=round(total_act - total_est, 2),
            overall_overrun_pct=overall_overrun,
        )

    def get_employee_utilization(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        current_user_id: uuid.UUID | None = None,
    ) -> UtilizationResponse:
        if not to_date:
            to_date = date.today()
        if not from_date:
            from_date = to_date - timedelta(days=30)

        # FIX 3: RBAC scoping
        from app.core.rbac import DataAccessLevel
        from app.services.dashboard.dashboard_common_service import DashboardCommonService

        user_ctx = None
        if current_user_id is not None:
            from app.core.rbac import get_user_context
            user_ctx = get_user_context(self.db, str(current_user_id))

        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        emp_stmt = select(Employee).where(Employee.is_active == True).order_by(Employee.first_name)
        if scoped_employee_ids is not None:
            emp_stmt = emp_stmt.where(Employee.id.in_(scoped_employee_ids))

        # For SELF level, restrict to only the current user
        if user_ctx and user_ctx.data_access_level == DataAccessLevel.SELF and current_user_id is not None:
            emp_stmt = select(Employee).where(
                Employee.is_active == True, Employee.id == current_user_id
            )

        employees = self.db.scalars(emp_stmt).all()
        employee_ids = [emp.id for emp in employees]

        if not employee_ids:
            return UtilizationResponse(
                employees=[], period_start=from_date, period_end=to_date, total_hours_company=0.0
            )

        # FIX 5: Batch pre-fetch all per-employee metrics before the loop

        # Batch 1: total hours logged per employee
        hours_map = {str(r[0]): float(r[1] or 0) for r in self.db.execute(
            select(TimeEntry.employee_id, func.sum(TimeEntry.hours_spent))
            .where(
                TimeEntry.employee_id.in_(employee_ids),
                TimeEntry.date >= from_date,
                TimeEntry.date <= to_date,
                TimeEntry.status != "REJECTED",
            )
            .group_by(TimeEntry.employee_id)
        ).all()}

        # Batch 2: billable hours per employee
        billable_map = {str(r[0]): float(r[1] or 0) for r in self.db.execute(
            select(TimeEntry.employee_id, func.sum(TimeEntry.hours_spent))
            .where(
                TimeEntry.employee_id.in_(employee_ids),
                TimeEntry.date >= from_date,
                TimeEntry.date <= to_date,
                TimeEntry.is_billable == True,
                TimeEntry.status != "REJECTED",
            )
            .group_by(TimeEntry.employee_id)
        ).all()}

        # Batch 3: distinct task count per employee
        task_count_map = {str(r[0]): int(r[1] or 0) for r in self.db.execute(
            select(TimeEntry.employee_id, func.count(func.distinct(TimeEntry.task_id)))
            .where(
                TimeEntry.employee_id.in_(employee_ids),
                TimeEntry.date >= from_date,
                TimeEntry.date <= to_date,
            )
            .group_by(TimeEntry.employee_id)
        ).all()}

        # Batch 4: late days per employee
        late_days_map = {str(r[0]): int(r[1] or 0) for r in self.db.execute(
            select(Attendance.employee_id, func.count(Attendance.id))
            .where(
                Attendance.employee_id.in_(employee_ids),
                Attendance.date >= from_date,
                Attendance.date <= to_date,
                Attendance.is_late == True,
            )
            .group_by(Attendance.employee_id)
        ).all()}

        # Batch 5: absence count per employee
        absence_map = {str(r[0]): int(r[1] or 0) for r in self.db.execute(
            select(Attendance.employee_id, func.count(Attendance.id))
            .where(
                Attendance.employee_id.in_(employee_ids),
                Attendance.date >= from_date,
                Attendance.date <= to_date,
                Attendance.status == "ABSENT",
            )
            .group_by(Attendance.employee_id)
        ).all()}

        # FIX 11: correct std_hours formula — 8 hours per working day
        working_days_in_period = (to_date - from_date).days + 1
        std_hours = round(working_days_in_period * 8, 1) if working_days_in_period > 0 else 160.0

        result = []
        total_company_hours = 0.0

        for emp in employees:
            key = str(emp.id)
            hours_logged = hours_map.get(key, 0.0)
            billable = billable_map.get(key, 0.0)
            task_count = task_count_map.get(key, 0)
            late_days = late_days_map.get(key, 0)
            absence_days = absence_map.get(key, 0)

            utilization_pct = round((hours_logged / std_hours * 100), 1) if std_hours > 0 else 0.0
            total_company_hours += hours_logged

            result.append(EmployeeUtilization(
                id=emp.id,
                employee_code=emp.employee_code,
                employee_name=f"{emp.first_name} {emp.last_name}",
                department_name=emp.department.name if emp.department else None,
                total_hours_logged=hours_logged,
                billable_hours=billable,
                task_count=task_count,
                late_days=late_days,
                absence_days=absence_days,
                utilization_percentage=utilization_pct,
            ))

        return UtilizationResponse(
            employees=result,
            period_start=from_date,
            period_end=to_date,
            total_hours_company=round(total_company_hours, 2),
        )

    def get_department_load(self) -> DepartmentLoadResponse:
        categories = self.db.scalars(
            select(func.distinct(Task.department_category)).where(
                Task.department_category.isnot(None), Task.is_active == True
            )
        ).all()

        result = []
        for cat in categories:
            if not cat:
                continue
            est = self.db.scalar(
                select(func.coalesce(func.sum(Task.estimated_hours), 0)).where(
                    Task.department_category == cat, Task.is_active == True
                )
            ) or 0
            act = self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0))
                .join(Task, TimeEntry.task_id == Task.id)
                .where(Task.department_category == cat, Task.is_active == True, TimeEntry.status != "REJECTED")
            ) or 0
            count = self.db.scalar(
                select(func.count(Task.id)).where(Task.department_category == cat, Task.is_active == True)
            ) or 0
            est_f = float(est)
            act_f = float(act)
            result.append(DepartmentLoad(
                department=cat,
                estimated_hours=est_f,
                actual_hours=act_f,
                task_count=count,
                overrun_percentage=round(((act_f - est_f) / est_f * 100) if est_f > 0 else 0, 1),
            ))

        return DepartmentLoadResponse(departments=result)

    def get_overdue_tasks(self, current_user_id: uuid.UUID | None = None) -> list[OverdueTask]:
        # FIX 2: RBAC scoping
        from app.core.rbac import DataAccessLevel
        from app.services.dashboard.dashboard_common_service import DashboardCommonService

        user_ctx = None
        if current_user_id is not None:
            from app.core.rbac import get_user_context
            user_ctx = get_user_context(self.db, str(current_user_id))

        today = date.today()
        stmt = (
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                Task.planned_delivery_date < today,
                Task.status.not_in(["COMPLETED", "CANCELLED"]),
                Task.is_active == True,
            )
            .order_by(Task.planned_delivery_date)
        )

        if user_ctx:
            if user_ctx.data_access_level == DataAccessLevel.SELF:
                # Only tasks assigned to the current user
                stmt = stmt.join(TaskAssignment, TaskAssignment.task_id == Task.id).where(
                    TaskAssignment.employee_id == user_ctx.employee_id
                )
            elif user_ctx.data_access_level == DataAccessLevel.TEAM:
                scoped_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx)
                if scoped_ids:
                    stmt = stmt.join(TaskAssignment, TaskAssignment.task_id == Task.id).where(
                        TaskAssignment.employee_id.in_(scoped_ids)
                    )
            # MANAGED/FULL: no additional filter

        tasks = self.db.execute(stmt).all()

        # Batch-fetch assignee names to avoid N+1
        task_ids = [row[0].id for row in tasks]
        assignee_map: dict[str, str] = {}
        if task_ids:
            assignee_rows = self.db.execute(
                select(TaskAssignment.task_id, Employee.first_name, Employee.last_name)
                .join(Employee, TaskAssignment.employee_id == Employee.id)
                .where(TaskAssignment.task_id.in_(task_ids))
                .distinct(TaskAssignment.task_id)
            ).all()
            for a_row in assignee_rows:
                assignee_map[str(a_row[0])] = f"{a_row[1]} {a_row[2] or ''}".strip()

        result = []
        for row in tasks:
            t = row[0]
            days_over = (today - t.planned_delivery_date).days if t.planned_delivery_date else 0
            result.append(OverdueTask(
                id=t.id,
                task_code=t.task_code,
                title=t.title,
                project_id=t.project_id,
                project_name=row[1],
                status=t.status,
                priority=t.priority,
                planned_delivery_date=t.planned_delivery_date,
                estimated_hours=float(t.estimated_hours or 0),
                actual_hours=float(t.actual_hours or 0),
                days_overdue=days_over,
                assignee_name=assignee_map.get(str(t.id)),
            ))

        return result

    def get_client_performance(self) -> ClientPerformanceResponse:
        clients = self.db.scalars(select(Client).where(Client.is_active == True).order_by(Client.name)).all()

        result = []
        for c in clients:
            projects = self.db.scalars(select(Project).where(Project.client_id == c.id)).all()
            total = len(projects)
            active = sum(1 for p in projects if p.status in ("In Progress", "On Hold"))
            completed = sum(1 for p in projects if p.status == "Completed")
            delayed = sum(1 for p in projects if p.actual_end_date and p.planned_end_date and p.actual_end_date > p.planned_end_date)
            est = sum(float(p.estimated_hours or 0) for p in projects)
            act = sum(
                float(self.db.scalar(
                    select(func.coalesce(func.sum(TimeEntry.hours_spent), 0))
                    .join(Task, TimeEntry.task_id == Task.id)
                    .where(Task.project_id == p2.id, TimeEntry.status != "REJECTED")
                ) or 0) for p2 in projects
            )
            on_time_pct = round(((completed - delayed) / completed * 100) if completed > 0 else 100.0, 1)

            result.append(ClientPerformance(
                id=c.id, name=c.name, total_projects=total,
                active_projects=active, completed_projects=completed,
                delayed_projects=delayed, total_estimated_hours=round(est, 2),
                total_actual_hours=round(act, 2), on_time_delivery_pct=on_time_pct,
            ))

        return ClientPerformanceResponse(clients=result)

    def get_scope_distribution(self) -> ScopeDistributionResponse:
        from app.models.scope_of_work import ScopeOfWork

        # FIX 10: Pre-fetch all scopes to avoid N+1 db.get() inside loop
        scopes_map = {str(s.id): s for s in self.db.scalars(select(ScopeOfWork)).all()}

        scope_rows = self.db.execute(
            select(
                Task.scope_of_work_id,
                func.coalesce(func.sum(Task.estimated_hours), 0),
                func.coalesce(func.sum(Task.actual_hours), 0),
                func.count(Task.id),
            )
            .where(Task.is_active == True, Task.scope_of_work_id.isnot(None))
            .group_by(Task.scope_of_work_id)
            .order_by(func.count(Task.id).desc())
        ).all()

        result = []
        for row in scope_rows:
            scope = scopes_map.get(str(row[0])) if row[0] else None
            result.append(ScopeDistribution(
                scope_code=scope.code if scope else None,
                scope_name=scope.name if scope else None,
                department_category=scope.department_category if scope else None,
                estimated_hours=float(row[1]),
                actual_hours=float(row[2]),
                task_count=row[3],
            ))

        no_scope_est = self.db.scalar(
            select(func.coalesce(func.sum(Task.estimated_hours), 0)).where(
                Task.is_active == True, Task.scope_of_work_id == None
            )
        ) or 0
        no_scope_act = self.db.scalar(
            select(func.coalesce(func.sum(Task.actual_hours), 0)).where(
                Task.is_active == True, Task.scope_of_work_id == None
            )
        ) or 0
        no_scope_count = self.db.scalar(
            select(func.count(Task.id)).where(Task.is_active == True, Task.scope_of_work_id == None)
        ) or 0
        if no_scope_count > 0:
            result.append(ScopeDistribution(
                scope_code=None, scope_name="Uncategorized",
                department_category=None,
                estimated_hours=float(no_scope_est),
                actual_hours=float(no_scope_act),
                task_count=no_scope_count,
            ))

        return ScopeDistributionResponse(scopes=result)

    def get_session_analytics(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        employee_id: UUID | None = None,
    ) -> SessionAnalyticsResponse:
        if not to_date:
            to_date = date.today()
        if not from_date:
            from_date = to_date - timedelta(days=30)

        base_filter = [
            TaskWorkSession.start_time >= datetime.combine(from_date, datetime.min.time()),
            TaskWorkSession.start_time <= datetime.combine(to_date, datetime.max.time()),
        ]

        employees_query = select(Employee).where(Employee.is_active == True)
        if employee_id:
            employees_query = employees_query.where(Employee.id == employee_id)
        employees = self.db.scalars(employees_query.order_by(Employee.first_name)).all()

        result = []
        total_company_session_hours = 0.0
        total_company_break_hours = 0.0

        for emp in employees:
            sessions = self.db.scalars(
                select(TaskWorkSession).where(
                    TaskWorkSession.employee_id == emp.id,
                    *base_filter,
                )
            ).all()

            breaks = self.db.scalars(
                select(EmployeeBreak).where(
                    EmployeeBreak.employee_id == emp.id,
                    EmployeeBreak.date >= from_date,
                    EmployeeBreak.date <= to_date,
                )
            ).all()

            total_session_min = sum(
                s.duration_minutes for s in sessions
                if s.status in ("COMPLETED", "CANCELLED", "ABANDONED")
            )
            total_break_min = sum(b.duration_minutes for b in breaks)
            session_count = len(sessions)
            avg_duration = round(total_session_min / session_count, 1) if session_count > 0 else 0.0

            session_hours = round(total_session_min / 60.0, 2)
            break_hours = round(total_break_min / 60.0, 2)

            billable_sessions = [
                s for s in sessions if s.session_type == "REGULAR"
                and s.status in ("COMPLETED", "CANCELLED", "ABANDONED")
            ]
            billable_min = sum(s.duration_minutes for s in billable_sessions)

            working_days_in_period = (to_date - from_date).days + 1
            expected_work_min = working_days_in_period * 480  # 8 hours per day
            idle_min = max(0, expected_work_min - total_session_min)

            total_company_session_hours += session_hours
            total_company_break_hours += break_hours

            result.append(SessionAnalytics(
                employee_id=emp.id,
                employee_name=f"{emp.first_name} {emp.last_name}",
                total_session_minutes=total_session_min,
                total_break_minutes=total_break_min,
                net_work_minutes=max(0, total_session_min - total_break_min),
                session_count=session_count,
                avg_session_duration_minutes=avg_duration,
                billable_session_hours=round(billable_min / 60.0, 2),
                idle_minutes=idle_min,
                period_start=from_date,
                period_end=to_date,
            ))

        return SessionAnalyticsResponse(
            employees=result,
            period_start=from_date,
            period_end=to_date,
            total_company_session_hours=round(total_company_session_hours, 2),
            total_company_break_hours=round(total_company_break_hours, 2),
        )

    def get_rework_analytics(self) -> ReworkAnalyticsResponse:
        total_rework_entries = self.db.scalar(
            select(func.count(TaskReworkHistory.id))
        ) or 0
        total_rework_hours = self.db.scalar(
            select(func.coalesce(func.sum(TaskReworkHistory.hours_spent), 0)).where(
                TaskReworkHistory.closed_at.isnot(None)
            )
        ) or 0
        open_cycles = self.db.scalar(
            select(func.count(TaskReworkHistory.id)).where(
                TaskReworkHistory.closed_at.is_(None)
            )
        ) or 0

        total_actual_hours = self.db.scalar(
            select(func.coalesce(func.sum(Task.actual_hours), 0)).where(
                Task.is_active == True
            )
        ) or 0

        total_rework_hours_f = float(total_rework_hours)
        total_actual_f = float(total_actual_hours)
        rework_pct = round(
            (total_rework_hours_f / total_actual_f * 100)
            if total_actual_f > 0 else 0, 2
        )
        avg_hours = round(
            total_rework_hours_f / total_rework_entries, 2
        ) if total_rework_entries > 0 else 0.0

        rework_by_task = self.db.execute(
            select(
                Task.id,
                Task.task_code,
                Task.title,
                func.count(TaskReworkHistory.id),
                func.coalesce(func.sum(TaskReworkHistory.hours_spent), 0),
            )
            .join(TaskReworkHistory, TaskReworkHistory.task_id == Task.id)
            .group_by(Task.id, Task.task_code, Task.title)
            .order_by(func.sum(TaskReworkHistory.hours_spent).desc())
        ).all()

        by_task_list = []
        for row in rework_by_task:
            by_task_list.append({
                "task_id": str(row[0]),
                "task_code": row[1],
                "title": row[2],
                "rework_count": row[3],
                "total_hours": float(row[4]),
            })

        return ReworkAnalyticsResponse(
            total_rework_tasks=total_rework_entries,
            total_rework_hours=round(total_rework_hours_f, 2),
            rework_cost_percentage=rework_pct,
            average_hours_per_rework=avg_hours,
            open_rework_cycles=open_cycles,
            rework_by_task=by_task_list,
        )

    def get_upcoming_deadlines(self, days: int = 14) -> list[OverdueTask]:
        today = date.today()
        cutoff = today + timedelta(days=days)
        tasks = self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                Task.planned_delivery_date >= today,
                Task.planned_delivery_date <= cutoff,
                Task.status.not_in(["COMPLETED", "CANCELLED"]),
                Task.is_active == True,
            )
            .order_by(Task.planned_delivery_date)
        ).all()

        # FIX 7: Batch-fetch assignee names to avoid N+1
        task_ids = [row[0].id for row in tasks]
        assignee_map: dict[str, str] = {}
        if task_ids:
            assignee_rows = self.db.execute(
                select(TaskAssignment.task_id, Employee.first_name, Employee.last_name)
                .join(Employee, TaskAssignment.employee_id == Employee.id)
                .where(TaskAssignment.task_id.in_(task_ids))
                .distinct(TaskAssignment.task_id)
            ).all()
            for a_row in assignee_rows:
                assignee_map[str(a_row[0])] = f"{a_row[1]} {a_row[2] or ''}".strip()

        result = []
        for row in tasks:
            t = row[0]
            result.append(OverdueTask(
                id=t.id, task_code=t.task_code, title=t.title,
                project_id=t.project_id, project_name=row[1],
                status=t.status, priority=t.priority,
                planned_delivery_date=t.planned_delivery_date,
                estimated_hours=float(t.estimated_hours or 0),
                actual_hours=float(t.actual_hours or 0),
                days_overdue=0,
                assignee_name=assignee_map.get(str(t.id)),
            ))
        return result

    def get_calendar_events(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        # DEPRECATED: Use CalendarService.get_events() via GET /api/v1/calendar/events
        events = []

        tasks = self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                Task.planned_delivery_date >= from_date,
                Task.planned_delivery_date <= to_date,
                Task.is_active == True,
            )
        ).all()

        STATUS_COLORS = {
            "NOT_STARTED": "#6B7280", "IN_PROGRESS": "#3B82F6",
            "ON_HOLD": "#F59E0B", "COMPLETED": "#10B981", "CANCELLED": "#EF4444",
        }

        for row in tasks:
            t = row[0]
            if t.planned_delivery_date:
                is_overdue = t.planned_delivery_date < date.today() and t.status not in ("COMPLETED", "CANCELLED")
                events.append({
                    "id": f"task-{t.id}",
                    "title": f"[{t.task_code}] {t.title[:40]}",
                    "start": t.planned_delivery_date.isoformat(),
                    "allDay": True,
                    "backgroundColor": STATUS_COLORS.get(t.status, "#6B7280"),
                    "borderColor": STATUS_COLORS.get(t.status, "#6B7280"),
                    "textColor": "#ffffff",
                    "extendedProps": {"type": "task", "status": t.status, "project": row[1], "task_code": t.task_code, "overdue": is_overdue},
                })

        employees = self.db.execute(
            select(Employee).where(
                Employee.is_active == True, Employee.date_of_birth.isnot(None)
            )
        ).scalars().all()

        for emp in employees:
            if emp.date_of_birth:
                bday_this_year = date(date.today().year, emp.date_of_birth.month, emp.date_of_birth.day)
                if from_date <= bday_this_year <= to_date:
                    events.append({
                        "id": f"bday-{emp.id}",
                        "title": f"\U0001F382 {emp.first_name}'s Birthday",
                        "start": bday_this_year.isoformat(),
                        "allDay": True,
                        "backgroundColor": "#EC4899",
                        "borderColor": "#EC4899",
                        "textColor": "#ffffff",
                        "extendedProps": {"type": "birthday"},
                    })

        return events
