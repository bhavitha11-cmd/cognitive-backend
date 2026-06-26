from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, func, and_, case
from sqlalchemy.orm import Session
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

    def get_dashboard_stats(self) -> DashboardStats:
        now = datetime.now()
        today = now.date()

        total_clients = self.db.scalar(select(func.count(Client.id)).where(Client.is_active == True)) or 0
        total_projects = self.db.scalar(select(func.count(Project.id)).where(Project.is_active == True)) or 0
        active_projects = self.db.scalar(select(func.count(Project.id)).where(Project.is_active == True, Project.status.in_(["In Progress", "On Hold"]))) or 0
        completed_projects = self.db.scalar(select(func.count(Project.id)).where(Project.status == "Completed")) or 0
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
        total_employees = self.db.scalar(select(func.count(Employee.id)).where(Employee.is_active == True)) or 0

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
            active_clients=self.db.scalar(select(func.count(Client.id)).where(Client.is_active == True)) or 0,
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

        result = []
        total_est = 0.0
        total_act = 0.0

        for p in projects:
            est = float(p.estimated_hours or 0)
            actual = self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0))
                .join(Task, TimeEntry.task_id == Task.id)
                .where(Task.project_id == p.id, TimeEntry.status != "REJECTED")
            ) or 0
            actual = float(actual)
            total_est += est
            total_act += actual

            task_count = self.db.scalar(select(func.count(Task.id)).where(Task.project_id == p.id, Task.is_active == True)) or 0
            completed = self.db.scalar(select(func.count(Task.id)).where(Task.project_id == p.id, Task.status == "COMPLETED")) or 0

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

    def get_employee_utilization(self, from_date: date | None = None, to_date: date | None = None) -> UtilizationResponse:
        if not to_date:
            to_date = date.today()
        if not from_date:
            from_date = to_date - timedelta(days=30)

        employees = self.db.scalars(
            select(Employee).where(Employee.is_active == True).order_by(Employee.first_name)
        ).all()

        result = []
        total_company_hours = 0.0

        for emp in employees:
            hours_logged = self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0)).where(
                    TimeEntry.employee_id == emp.id,
                    TimeEntry.date >= from_date,
                    TimeEntry.date <= to_date,
                    TimeEntry.status != "REJECTED",
                )
            ) or 0
            hours_logged = float(hours_logged)

            billable = self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0)).where(
                    TimeEntry.employee_id == emp.id,
                    TimeEntry.date >= from_date,
                    TimeEntry.date <= to_date,
                    TimeEntry.is_billable == True,
                    TimeEntry.status != "REJECTED",
                )
            ) or 0
            billable = float(billable)

            task_count = self.db.scalar(
                select(func.count(func.distinct(TimeEntry.task_id))).where(
                    TimeEntry.employee_id == emp.id,
                    TimeEntry.date >= from_date,
                    TimeEntry.date <= to_date,
                )
            ) or 0

            late_days = self.db.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.employee_id == emp.id,
                    Attendance.date >= from_date,
                    Attendance.date <= to_date,
                    Attendance.is_late == True,
                )
            ) or 0

            absence_days = self.db.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.employee_id == emp.id,
                    Attendance.date >= from_date,
                    Attendance.date <= to_date,
                    Attendance.status == "ABSENT",
                )
            ) or 0

            working_days_in_period = (to_date - from_date).days + 1
            std_hours = round(working_days_in_period / 30 * 160, 1) if working_days_in_period > 0 else 160

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

    def get_overdue_tasks(self) -> list[OverdueTask]:
        today = date.today()
        tasks = self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                Task.planned_delivery_date < today,
                Task.status.not_in(["COMPLETED", "CANCELLED"]),
                Task.is_active == True,
            )
            .order_by(Task.planned_delivery_date)
        ).all()

        result = []
        for row in tasks:
            t = row[0]
            days_over = (today - t.planned_delivery_date).days if t.planned_delivery_date else 0

            assignee = self.db.scalar(
                select(func.concat(Employee.first_name, " ", Employee.last_name))
                .join(TaskAssignment, TaskAssignment.employee_id == Employee.id)
                .where(TaskAssignment.task_id == t.id)
                .limit(1)
            )

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
                assignee_name=assignee,
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
        scopes = self.db.execute(
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
        for row in scopes:
            from app.models.scope_of_work import ScopeOfWork
            scope = self.db.get(ScopeOfWork, row[0]) if row[0] else None
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
                assignee_name=None,
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
