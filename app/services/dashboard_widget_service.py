from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select, func, extract
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import selectinload

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
        stmt = (
            select(Employee)
            .where(
                Employee.is_active == True,
                Employee.date_of_birth.isnot(None),
                extract('month', Employee.date_of_birth) == today.month,
                extract('day', Employee.date_of_birth) == today.day,
            )
        )
        employees = self.db.scalars(stmt).all()

        results: list[BirthdayInfo] = []
        for emp in employees:
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

        # Build a set of (month, day) pairs for the window, pushing filter to DB
        day_pairs: list[tuple[int, int]] = []
        curr = today
        while curr <= end:
            try:
                # Validate the day exists (handles leap year edge cases)
                date(today.year, curr.month, curr.day)
                day_pairs.append((curr.month, curr.day))
            except ValueError:
                # Feb 29 in non-leap year — use Feb 28 instead
                day_pairs.append((2, 28))
            curr += timedelta(days=1)

        from sqlalchemy import or_, and_
        month_day_filters = [
            and_(
                extract('month', Employee.date_of_birth) == m,
                extract('day', Employee.date_of_birth) == d,
            )
            for m, d in set(day_pairs)
        ]
        stmt = (
            select(Employee)
            .where(
                Employee.is_active == True,
                Employee.date_of_birth.isnot(None),
                or_(*month_day_filters) if month_day_filters else False,
            )
        )
        employees = self.db.scalars(stmt).all()

        results: list[BirthdayInfo] = []
        for emp in employees:
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
            .options(joinedload(Task.project))
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
        from app.core.rbac import get_user_context, DataAccessLevel
        today = date.today()
        end = today + timedelta(days=days)
        stmt = (
            select(Project)
            .options(joinedload(Project.project_manager))
            .where(
                Project.is_active == True,
                Project.planned_end_date.between(today, end),
                Project.status.notin_(["Completed", "Cancelled"]),
            )
        )

        if self.current_user_id:
            ctx = get_user_context(self.db, str(self.current_user_id))
            if ctx.data_access_level == DataAccessLevel.MANAGED:
                stmt = stmt.where(Project.project_manager_id == self.current_user_id)
            elif ctx.data_access_level in (DataAccessLevel.TEAM, DataAccessLevel.SELF):
                from app.models.task_assignment import TaskAssignment as _TA
                from app.models.project_member import ProjectMember
                accessible_project_ids = self.db.scalars(
                    select(ProjectMember.project_id).where(
                        ProjectMember.employee_id == self.current_user_id
                    )
                ).all()
                if not accessible_project_ids:
                    # Fall back to projects via task assignment
                    accessible_project_ids = self.db.scalars(
                        select(Task.project_id)
                        .join(_TA, _TA.task_id == Task.id)
                        .where(_TA.employee_id == self.current_user_id)
                    ).all()
                stmt = stmt.where(Project.id.in_(accessible_project_ids))
            # DataAccessLevel.FULL: keep all

        projects = self.db.scalars(stmt).all()

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
        from app.core.rbac import get_user_context, DataAccessLevel
        today = date.today()
        stmt = (
            select(Task)
            .options(
                joinedload(Task.project),
                selectinload(Task.assignments).joinedload(TaskAssignment.employee),
            )
            .where(
                Task.is_active == True,
                Task.planned_delivery_date < today,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
            )
        )

        if self.current_user_id:
            ctx = get_user_context(self.db, str(self.current_user_id))
            if ctx.data_access_level == DataAccessLevel.SELF:
                assigned_task_ids = self.db.scalars(
                    select(TaskAssignment.task_id).where(
                        TaskAssignment.employee_id == self.current_user_id,
                    )
                ).all()
                stmt = stmt.where(Task.id.in_(assigned_task_ids))
            elif ctx.data_access_level == DataAccessLevel.TEAM:
                # Tasks in projects where the user is a member
                from app.models.project_member import ProjectMember
                accessible_project_ids = self.db.scalars(
                    select(ProjectMember.project_id).where(
                        ProjectMember.employee_id == self.current_user_id
                    )
                ).all()
                stmt = stmt.where(Task.project_id.in_(accessible_project_ids))
            elif ctx.data_access_level == DataAccessLevel.MANAGED:
                stmt = stmt.where(
                    Task.project_id.in_(
                        select(Project.id).where(
                            Project.project_manager_id == self.current_user_id
                        )
                    )
                )
            # DataAccessLevel.FULL: keep all

        tasks = self.db.scalars(stmt).all()

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

    def get_pending_schedule_reviews(self) -> list:
        """Return PENDING schedule reviews for the currently authenticated user.

        Uses the same RBAC pattern as ``get_today_tasks``:
        - Super-admins / full data-access users receive all pending reviews
          across all project managers.
        - Everyone else receives only reviews where they are the assigned
          project manager.

        Returns a list of ``PendingScheduleReviewWidget`` objects.
        """
        from app.core.rbac import get_user_context, DataAccessLevel
        from app.services.pending_schedule_review_service import PendingScheduleReviewService

        svc = PendingScheduleReviewService(self.db, self.current_user_id)

        if self.current_user_id:
            ctx = get_user_context(self.db, str(self.current_user_id))
            if ctx.data_access_level == DataAccessLevel.FULL:
                return svc.get_widget_data_all()
            return svc.get_widget_data_for_manager(self.current_user_id)

        return []
