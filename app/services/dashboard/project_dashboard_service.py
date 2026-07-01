from datetime import date, datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session, joinedload
from app.models.project import Project
from app.models.task import Task
from app.models.time_entry import TimeEntry
from app.models.employee import Employee
from app.schemas.dashboard_analytics import (
    ProjectSummary,
    ProjectCharts,
    BurnCurvePoint,
    DailyProgressPoint,
    TaskTimeSummary
)

class ProjectDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, project_id: UUID) -> ProjectSummary:
        project = self.db.execute(
            select(Project)
            .options(
                joinedload(Project.client),
                joinedload(Project.department),
                joinedload(Project.project_manager)
            )
            .where(Project.id == project_id, Project.is_active == True)
        ).scalar_one_or_none()

        if not project:
            raise ValueError("Project not found or inactive")

        # Task counts
        total_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.project_id == project_id, Task.is_active == True)) or 0
        completed_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.project_id == project_id, Task.is_active == True, Task.status == "COMPLETED")) or 0
        in_progress_tasks = self.db.scalar(select(func.count(Task.id)).where(Task.project_id == project_id, Task.is_active == True, Task.status == "IN_PROGRESS")) or 0

        planned = float(project.estimated_hours or 0.0)
        actual = float(project.actual_hours or 0.0)
        remaining = max(0.0, planned - actual)
        progress = float(project.progress or 0.0)

        customer_name = project.client.name if project.client else None
        dept_name = project.department.name if project.department else None
        pm_name = f"{project.project_manager.first_name} {project.project_manager.last_name or ''}".strip() if project.project_manager else None

        return ProjectSummary(
            id=project.id,
            project_code=project.project_code,
            name=project.name,
            customer_name=customer_name,
            department_name=dept_name,
            project_manager_name=pm_name,
            planned_hours=planned,
            actual_hours=actual,
            remaining_hours=remaining,
            completion_percentage=progress,
            delivery_date=project.planned_end_date,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            in_progress_tasks=in_progress_tasks
        )

    def get_charts(self, project_id: UUID) -> ProjectCharts:
        project = self.db.scalar(
            select(Project).where(Project.id == project_id, Project.is_active == True)
        )
        if not project:
            raise ValueError("Project not found or inactive")

        # 1. Task Status Counts
        statuses_query = self.db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.project_id == project_id, Task.is_active == True)
            .group_by(Task.status)
        ).all()
        task_statuses = [{"status": row[0], "count": row[1]} for row in statuses_query]

        # 2. Daily progress (actual hours logged in the last 30 days)
        start_day = date.today() - timedelta(days=30)
        daily_query = self.db.execute(
            select(TimeEntry.date, func.sum(TimeEntry.hours_spent))
            .where(
                TimeEntry.project_id == project_id,
                TimeEntry.date >= start_day,
                TimeEntry.status != "REJECTED"
            )
            .group_by(TimeEntry.date)
            .order_by(TimeEntry.date)
        ).all()
        daily_progress = [DailyProgressPoint(date=row[0], hours_logged=float(row[1])) for row in daily_query]

        # 3. Top time consuming tasks (top 5 by actual_hours)
        top_tasks = self.db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.is_active == True)
            .order_by(Task.actual_hours.desc())
            .limit(5)
        ).all()
        top_time_consuming_tasks = [
            TaskTimeSummary(
                id=t.id,
                task_code=t.task_code,
                title=t.title,
                actual_hours=float(t.actual_hours),
                estimated_hours=float(t.estimated_hours)
            )
            for t in top_tasks
        ]

        # 4. Burn Curve (Planned Cumulative vs Actual Cumulative)
        # We look at dates from project start date to delivery date (or today if project has run past delivery date)
        start_date = project.planned_start_date or (date.today() - timedelta(days=30))
        end_date = project.planned_end_date or date.today()
        if end_date < date.today():
            end_date = date.today()

        burn_curve = []
        curr_date = start_date
        
        # Calculate daily allocations
        # Let's map planned hours by day
        tasks = self.db.scalars(
            select(Task)
            .where(Task.project_id == project_id, Task.is_active == True)
        ).all()
        
        daily_planned_map = {}
        for t in tasks:
            if t.planned_start_date and t.planned_end_date:
                days = (t.planned_end_date - t.planned_start_date).days + 1
                hours_per_day = float(t.estimated_hours) / max(1, days)
                t_curr = t.planned_start_date
                while t_curr <= t.planned_end_date:
                    daily_planned_map[t_curr] = daily_planned_map.get(t_curr, 0.0) + hours_per_day
                    t_curr += timedelta(days=1)

        # Get daily actual hours map
        actual_query = self.db.execute(
            select(TimeEntry.date, func.sum(TimeEntry.hours_spent))
            .where(TimeEntry.project_id == project_id, TimeEntry.status != "REJECTED")
            .group_by(TimeEntry.date)
        ).all()
        daily_actual_map = {row[0]: float(row[1]) for row in actual_query}

        planned_cum = 0.0
        actual_cum = 0.0
        
        # Limit points to avoid excessive payload
        interval = max(1, (end_date - start_date).days // 30)
        day_count = 0

        while curr_date <= end_date:
            planned_cum += daily_planned_map.get(curr_date, 0.0)
            actual_cum += daily_actual_map.get(curr_date, 0.0)

            # Only record progress snapshots
            if day_count % interval == 0 or curr_date == end_date:
                burn_curve.append(BurnCurvePoint(
                    date=curr_date,
                    planned_cumulative_hours=round(planned_cum, 2),
                    actual_cumulative_hours=round(actual_cum, 2) if curr_date <= date.today() else 0.0
                ))
            curr_date += timedelta(days=1)
            day_count += 1

        return ProjectCharts(
            task_statuses=task_statuses,
            burn_curve=burn_curve,
            daily_progress=daily_progress,
            top_time_consuming_tasks=top_time_consuming_tasks
        )
