from datetime import date, datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.time_entry import TimeEntry
from app.models.attendance import Attendance
from app.models.project import Project
from app.services.dashboard.dashboard_common_service import DashboardCommonService
from app.services.productivity.kpi_calculator import KPICalculator
from app.services.productivity.policy_resolver import PolicyResolver
from app.schemas.dashboard_analytics import EmployeeSummary, EmployeeCharts

class EmployeeDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, employee_id: UUID) -> EmployeeSummary:
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_month = date(today.year, today.month, 1)

        # 1. Task counts
        today_tasks = self.db.scalar(
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == employee_id,
                Task.planned_delivery_date == today,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
                Task.is_active == True
            )
        ) or 0

        upcoming_tasks = self.db.scalar(
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == employee_id,
                Task.planned_start_date > today,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
                Task.is_active == True
            )
        ) or 0

        completed_tasks = self.db.scalar(
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == employee_id,
                Task.status == "COMPLETED",
                Task.is_active == True
            )
        ) or 0

        pending_tasks = self.db.scalar(
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id == employee_id,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
                Task.is_active == True
            )
        ) or 0

        # 2. Hours logged
        today_hours = float(self.db.scalar(
            select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date == today,
                TimeEntry.status != "REJECTED"
            )
        ) or 0.0)

        weekly_hours = float(self.db.scalar(
            select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date >= start_of_week,
                TimeEntry.date <= today,
                TimeEntry.status != "REJECTED"
            )
        ) or 0.0)

        monthly_hours = float(self.db.scalar(
            select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date >= start_of_month,
                TimeEntry.date <= today,
                TimeEntry.status != "REJECTED"
            )
        ) or 0.0)

        # 3. Target / Remaining (For the current week)
        weekly_cap = DashboardCommonService.get_expected_available_hours(employee_id, start_of_week, start_of_week + timedelta(days=6), self.db)
        remaining_hours = max(0.0, weekly_cap - weekly_hours)

        # 4. Today's Productivity (via KPICalculator)
        rule = PolicyResolver.get_rule(self.db)
        now_utc = datetime.utcnow()
        raw = KPICalculator.calculate_raw_metrics(self.db, employee_id, today, now_utc)
        compiled = KPICalculator.compile_kpi_metrics(raw, rule)
        prod_pct = compiled.get("productivity_percentage", {}).get("percentage", 0.0)

        return EmployeeSummary(
            today_tasks_count=today_tasks,
            upcoming_tasks_count=upcoming_tasks,
            completed_tasks_count=completed_tasks,
            pending_tasks_count=pending_tasks,
            today_hours=today_hours,
            weekly_hours=weekly_hours,
            monthly_hours=monthly_hours,
            remaining_hours=remaining_hours,
            personal_productivity_percentage=prod_pct
        )

    def get_charts(self, employee_id: UUID) -> EmployeeCharts:
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())

        # 1. Daily Hours (last 7 calendar days)
        daily_hours = []
        for i in range(7):
            day = today - timedelta(days=i)
            hrs = float(self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                    TimeEntry.employee_id == employee_id,
                    TimeEntry.date == day,
                    TimeEntry.status != "REJECTED"
                )
            ) or 0.0)
            daily_hours.append({
                "date": day.isoformat(),
                "hoursLogged": hrs
            })
        daily_hours.reverse()

        # 2. Weekly Trend (last 4 weeks)
        weekly_trend = []
        for i in range(4):
            w_start = start_of_week - timedelta(weeks=i)
            w_end = w_start + timedelta(days=6)
            hrs = float(self.db.scalar(
                select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                    TimeEntry.employee_id == employee_id,
                    TimeEntry.date >= w_start,
                    TimeEntry.date <= w_end,
                    TimeEntry.status != "REJECTED"
                )
            ) or 0.0)
            weekly_trend.append({
                "weekLabel": f"W-{i}",
                "hoursLogged": hrs
            })
        weekly_trend.reverse()

        # 3. Hours distribution by Project (last 30 days)
        distribution_query = self.db.execute(
            select(Project.name, func.sum(TimeEntry.hours_spent))
            .join(Project, TimeEntry.project_id == Project.id)
            .where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date >= today - timedelta(days=30),
                TimeEntry.status != "REJECTED"
            )
            .group_by(Project.name)
        ).all()
        hours_distribution_by_project = [{"projectName": row[0], "hoursLogged": float(row[1])} for row in distribution_query]

        # 4. Timesheet Status Summary (last 30 days)
        status_query = self.db.execute(
            select(TimeEntry.status, func.count(TimeEntry.id))
            .where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date >= today - timedelta(days=30)
            )
            .group_by(TimeEntry.status)
        ).all()
        timesheet_status_summary = [{"status": row[0], "count": row[1]} for row in status_query]

        return EmployeeCharts(
            daily_hours=daily_hours,
            weekly_trend=weekly_trend,
            hours_distribution_by_project=hours_distribution_by_project,
            timesheet_status_summary=timesheet_status_summary
        )
