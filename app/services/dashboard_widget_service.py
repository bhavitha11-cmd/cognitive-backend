from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.schemas.dashboard_widget import (
    BirthdayInfo,
    DelayedTaskInfo,
    HolidayInfo,
    ProjectDeliveryInfo,
    TaskDueInfo,
    TodayEvent,
)
from app.services.calendar_service import CalendarService
from app.services.holiday_service import HolidayService


class DashboardWidgetService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_today_events(self) -> list[TodayEvent]:
        today = date.today()
        svc = CalendarService(self.db, self.current_user_id)
        events = svc.get_events(today, today)
        return [
            TodayEvent(
                id=e.id,
                title=e.title,
                type=(e.extendedProps or {}).get("type", "event"),
                date=e.start,
                color=e.backgroundColor,
            )
            for e in events
        ]

    def get_today_birthdays(self) -> list[BirthdayInfo]:
        today = date.today()
        employees = self.db.scalars(
            select(Employee).where(
                Employee.is_active == True,
                Employee.date_of_birth.isnot(None),
            )
        ).all()

        results: list[BirthdayInfo] = []
        for emp in employees:
            if not emp.date_of_birth:
                continue
            try:
                bday = date(today.year, emp.date_of_birth.month, emp.date_of_birth.day)
            except ValueError:
                bday = date(today.year, 3, 1)
            if bday == today:
                dept_name = None
                if emp.department:
                    dept_name = getattr(emp.department, "name", None)
                results.append(
                    BirthdayInfo(
                        id=emp.id,
                        name=f"{emp.first_name} {emp.last_name or ''}".strip(),
                        department=dept_name,
                    )
                )
        return results

    def get_upcoming_holidays(self, days: int = 30) -> list[HolidayInfo]:
        svc = HolidayService(self.db, self.current_user_id)
        holidays = svc.get_upcoming(days)
        return [
            HolidayInfo(
                id=h.id,
                name=h.name,
                date=h.date,
                holiday_type=h.holiday_type,
            )
            for h in holidays
        ]

    def get_upcoming_birthdays(self, days: int = 7) -> list[BirthdayInfo]:
        today = date.today()
        end = today + timedelta(days=days)
        employees = self.db.scalars(
            select(Employee).where(
                Employee.is_active == True,
                Employee.date_of_birth.isnot(None),
            )
        ).all()

        results: list[BirthdayInfo] = []
        for emp in employees:
            if not emp.date_of_birth:
                continue
            try:
                bday = date(today.year, emp.date_of_birth.month, emp.date_of_birth.day)
            except ValueError:
                bday = date(today.year, 3, 1)

            if today <= bday <= end:
                dept_name = None
                if emp.department:
                    dept_name = getattr(emp.department, "name", None)
                results.append(
                    BirthdayInfo(
                        id=emp.id,
                        name=f"{emp.first_name} {emp.last_name or ''}".strip(),
                        department=dept_name,
                    )
                )
        return results

    def get_today_tasks(self) -> list[TaskDueInfo]:
        today = date.today()
        stmt = (
            select(Task)
            .where(
                Task.planned_delivery_date == today,
                Task.is_active == True,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
            )
        )
        if self.current_user_id:
            from app.core.rbac import get_user_context, DataAccessLevel
            ctx = get_user_context(self.db, str(self.current_user_id))
            if ctx.data_access_level == DataAccessLevel.SELF:
                assigned_task_ids = self.db.scalars(
                    select(TaskAssignment.task_id).where(
                        TaskAssignment.employee_id == self.current_user_id,
                    )
                ).all()
                stmt = stmt.where(Task.id.in_(assigned_task_ids))

        tasks = self.db.scalars(stmt).all()
        return [
            TaskDueInfo(
                id=t.id,
                task_code=t.task_code,
                title=t.title,
                project_name=t.project.name if t.project else None,
                status=t.status,
            )
            for t in tasks
        ]

    def get_project_deliveries(self, days: int = 30) -> list[ProjectDeliveryInfo]:
        today = date.today()
        end = today + timedelta(days=days)
        projects = self.db.scalars(
            select(Project).where(
                Project.is_active == True,
                Project.planned_end_date.between(today, end),
                Project.status.notin_(["Completed", "Cancelled"]),
            )
        ).all()

        return [
            ProjectDeliveryInfo(
                id=p.id,
                name=p.name,
                planned_end_date=p.planned_end_date,
                project_manager=(
                    f"{p.project_manager.first_name} {p.project_manager.last_name}"
                    if p.project_manager else None
                ),
                is_delayed=today > p.planned_end_date,
            )
            for p in projects
        ]

    def get_delayed_tasks(self) -> list[DelayedTaskInfo]:
        today = date.today()
        tasks = self.db.scalars(
            select(Task).where(
                Task.is_active == True,
                Task.planned_delivery_date < today,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
            )
        ).all()

        results: list[DelayedTaskInfo] = []
        for t in tasks:
            assigned_to = None
            if t.assignments:
                first = t.assignments[0]
                if first.employee:
                    assigned_to = f"{first.employee.first_name} {first.employee.last_name}"
            results.append(
                DelayedTaskInfo(
                    id=t.id,
                    task_code=t.task_code,
                    title=t.title,
                    project_name=t.project.name if t.project else None,
                    days_overdue=(today - t.planned_delivery_date).days,
                    assigned_to=assigned_to,
                )
            )
        return results

    def get_tasks_requiring_reassignment(self) -> list[dict]:
        from app.models.task_continuity import TaskRisk
        from sqlalchemy.orm import joinedload
        today = date.today()
        risks = self.db.scalars(
            select(TaskRisk)
            .options(
                joinedload(TaskRisk.task),
                joinedload(TaskRisk.project),
                joinedload(TaskRisk.employee),
                joinedload(TaskRisk.leave_request)
            )
            .where(TaskRisk.status == "PENDING_MANAGER_ACTION")
        ).all()

        results = []
        for r in risks:
            days_rem = 0
            if r.task.planned_delivery_date:
                days_rem = max(0, (r.task.planned_delivery_date - today).days)

            leave_dur = float(r.leave_request.total_days)

            emp_name = f"{r.employee.first_name} {r.employee.last_name or ''}".strip()
            results.append({
                "project_id": str(r.project_id),
                "project_name": r.project.name,
                "task_id": str(r.task_id),
                "task_code": r.task.task_code,
                "task_title": r.task.title,
                "employee_id": str(r.employee_id),
                "employee_name": emp_name,
                "remaining_hours": float(r.remaining_hours),
                "days_remaining": days_rem,
                "leave_duration": leave_dur,
                "suggested_impact": r.project_impact or "",
            })
        return results

    def get_continuity_dashboard_kpis(self) -> dict:
        from app.models.task_continuity import TaskRisk, TaskTransferHistory
        from app.models.employee import Employee
        from app.services.planning_service import PlanningService
        from sqlalchemy import select
        from collections import defaultdict

        pending_risks = self.db.scalars(
            select(TaskRisk).where(TaskRisk.status == "PENDING_MANAGER_ACTION")
        ).all()

        emp_on_leave = len({r.employee_id for r in pending_risks})
        tasks_at_risk = len({r.task_id for r in pending_risks})
        projects_at_risk = len({r.project_id for r in pending_risks})

        # Calculate utilization for each employee for the next 30 days
        employees = self.db.scalars(select(Employee).where(Employee.is_active == True)).all()
        today = date.today()
        end_date = today + timedelta(days=30)

        available_count = 0
        overloaded_count = 0
        total_utilization = 0.0

        planning_svc = PlanningService(self.db)
        for emp in employees:
            try:
                cap = planning_svc.get_employee_capacity(emp.id, today, end_date)
                utils = [w.utilization_pct for w in cap.weeks]
                avg_util = sum(utils) / len(utils) if utils else 0.0
            except Exception:
                avg_util = 0.0

            if avg_util < 50.0:
                available_count += 1
            if avg_util > 100.0:
                overloaded_count += 1
            total_utilization += avg_util

        avg_utilization_all = round(total_utilization / len(employees) if employees else 0.0, 1)

        # Reassignment Trend (last 6 months)
        six_months_ago = datetime.now() - timedelta(days=180)
        transfers = self.db.scalars(
            select(TaskTransferHistory)
            .where(TaskTransferHistory.transfer_date >= six_months_ago)
        ).all()

        trend = defaultdict(int)
        for t in transfers:
            month_str = t.transfer_date.strftime("%Y-%m")
            trend[month_str] += 1

        # Fill in missing months to ensure trend structure is nice
        # e.g., last 6 months
        trend_dict = dict(sorted(trend.items()))

        return {
            "employees_on_leave_with_active_tasks": emp_on_leave,
            "tasks_at_risk": tasks_at_risk,
            "projects_at_risk": projects_at_risk,
            "upcoming_resource_shortage": overloaded_count,
            "available_engineers_count": available_count,
            "overloaded_engineers_count": overloaded_count,
            "resource_utilization_pct": avg_utilization_all,
            "reassignment_trend": trend_dict,
        }

