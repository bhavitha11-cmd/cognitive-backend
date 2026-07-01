from datetime import date, datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload, selectinload
from app.models.employee import Employee
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.time_entry import TimeEntry
from app.models.task_rework_history import TaskReworkHistory
from app.models.team_member import TeamMember
from app.models.team import Team
from app.models.employee_schedule import EmployeeSchedule
from app.services.dashboard.dashboard_common_service import DashboardCommonService
from app.services.productivity.kpi_calculator import KPICalculator
from app.services.productivity.policy_resolver import PolicyResolver
from app.schemas.dashboard_analytics import EmployeePerformanceRow

class EmployeePerformanceService:
    def __init__(self, db: Session):
        self.db = db

    def get_rankings(
        self,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        user_ctx = None
    ) -> list[EmployeePerformanceRow]:
        today = date.today()
        if not from_date:
            from_date = today - timedelta(days=30)
        if not to_date:
            to_date = today

        # 1. Base query for employees — FIX 9: eager-load department and team memberships
        stmt = (
            select(Employee)
            .options(
                joinedload(Employee.department),
                selectinload(Employee.team_memberships).joinedload(TeamMember.team),
            )
            .where(Employee.is_active == True)
        )
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        if team_id:
            stmt = stmt.join(TeamMember, TeamMember.employee_id == Employee.id).where(TeamMember.team_id == team_id)

        # Scoping context: only see under people
        scoped_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None
        if scoped_ids is not None:
            stmt = stmt.where(Employee.id.in_(scoped_ids))
        
        employees = self.db.scalars(stmt).all()
        employee_ids = [emp.id for emp in employees]
        if not employee_ids:
            return []

        rows = []

        from datetime import timezone
        rule = PolicyResolver.get_rule(self.db)
        now_utc = datetime.now(timezone.utc)

        # Batch Query 1: working days in period (run once!)
        working_days = DashboardCommonService.get_working_days_in_period(from_date, to_date, self.db)

        # Batch Query 2: primary team names for all employees
        team_stmt = (
            select(TeamMember.employee_id, Team.team_name)
            .join(Team, TeamMember.team_id == Team.id)
            .where(TeamMember.employee_id.in_(employee_ids), TeamMember.is_primary_team == True)
        )
        team_names = {row.employee_id: row.team_name for row in self.db.execute(team_stmt).all()}

        # Batch Query 3: latest available hours schedule per employee
        schedules_stmt = (
            select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
            .where(EmployeeSchedule.employee_id.in_(employee_ids))
            .order_by(EmployeeSchedule.week_start_date.desc())
        )
        latest_schedules = {}
        for emp_id, avail in self.db.execute(schedules_stmt).all():
            if emp_id not in latest_schedules:
                latest_schedules[emp_id] = float(avail)

        # Batch Query 4: actual APPROVED hours logged in timesheets
        actual_hours_stmt = (
            select(TimeEntry.employee_id, func.sum(TimeEntry.hours_spent))
            .where(
                TimeEntry.employee_id.in_(employee_ids),
                TimeEntry.date >= from_date,
                TimeEntry.date <= to_date,
                TimeEntry.status == "APPROVED"
            )
            .group_by(TimeEntry.employee_id)
        )
        actual_hours_map = {row[0]: float(row[1] or 0.0) for row in self.db.execute(actual_hours_stmt).all()}

        # Batch Query 5: assigned tasks overlapping date range
        tasks_stmt = (
            select(TaskAssignment.employee_id, Task)
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id.in_(employee_ids),
                Task.is_active == True,
                Task.planned_start_date <= to_date,
                Task.planned_end_date >= from_date
            )
        )
        tasks_by_emp = {}
        for emp_id, task in self.db.execute(tasks_stmt).all():
            tasks_by_emp.setdefault(emp_id, []).append(task)

        # Batch Query 6: rework hours logged
        rework_hours_stmt = (
            select(TaskAssignment.employee_id, func.sum(TaskReworkHistory.hours_spent))
            .join(TaskReworkHistory, TaskAssignment.task_id == TaskReworkHistory.task_id)
            .where(
                TaskAssignment.employee_id.in_(employee_ids),
                TaskReworkHistory.created_at >= datetime.combine(from_date, datetime.min.time()),
                TaskReworkHistory.created_at <= datetime.combine(to_date, datetime.max.time())
            )
            .group_by(TaskAssignment.employee_id)
        )
        rework_hours_map = {row[0]: float(row[1] or 0.0) for row in self.db.execute(rework_hours_stmt).all()}

        # Batch Query 7: timesheet compliance submitted days
        submitted_days_stmt = (
            select(TimeEntry.employee_id, func.count(func.distinct(TimeEntry.date)))
            .where(
                TimeEntry.employee_id.in_(employee_ids),
                TimeEntry.date >= from_date,
                TimeEntry.date <= to_date,
                TimeEntry.status.in_(["SUBMITTED", "APPROVED"])
            )
            .group_by(TimeEntry.employee_id)
        )
        submitted_days_map = {row[0]: int(row[1] or 0) for row in self.db.execute(submitted_days_stmt).all()}

        # Batch Query 8: daily productivity today raw metrics
        batch_raw_metrics = KPICalculator.calculate_raw_metrics_batch(self.db, employee_ids, today, now_utc)

        for emp in employees:
            dept_name = emp.department.name if emp.department else None
            team_name = team_names.get(emp.id)
            if not team_name and emp.team_assignments:
                team_name = emp.team_assignments[0].team.team_name

            # Hours logged
            actual_hours = actual_hours_map.get(emp.id, 0.0)

            # Planned capacity
            weekly_hours = latest_schedules.get(emp.id, 40.0)
            capacity = working_days * (weekly_hours / 5.0)
            utilization_pct = (actual_hours / capacity * 100) if capacity > 0 else 0.0

            # Tasks Metrics
            assigned_tasks = tasks_by_emp.get(emp.id, [])
            total_tasks_count = len(assigned_tasks)
            completed_tasks_count = sum(1 for t in assigned_tasks if t.status == "COMPLETED")
            task_completion_pct = (completed_tasks_count / total_tasks_count * 100) if total_tasks_count > 0 else 0.0

            planned_hours = sum(float(t.estimated_hours or 0.0) for t in assigned_tasks)
            variance_hours = actual_hours - planned_hours
            average_hours_per_task = (actual_hours / total_tasks_count) if total_tasks_count > 0 else 0.0

            # Average delay days
            completed_tasks_with_dates = [
                t for t in assigned_tasks 
                if t.status == "COMPLETED" and t.actual_delivery_date and t.planned_delivery_date
            ]
            total_delay = sum(
                (t.actual_delivery_date - t.planned_delivery_date).days
                for t in completed_tasks_with_dates
            )
            average_delay_days = (total_delay / len(completed_tasks_with_dates)) if completed_tasks_with_dates else 0.0

            # Rework Hours
            rework_hours = rework_hours_map.get(emp.id, 0.0)

            # Productivity Score
            raw_metrics = batch_raw_metrics.get(emp.id, {"presence_seconds": 0, "break_seconds": 0, "productive_seconds": 0})
            compiled = KPICalculator.compile_kpi_metrics(raw_metrics, rule)
            productivity_score = compiled.get("productivity_percentage", {}).get("percentage", 0.0)

            # Efficiency Score — FIX 8: cap at 999.9, floor at 0
            completed_assigned_tasks = [t for t in assigned_tasks if t.status == "COMPLETED"]
            completed_planned = sum(float(t.estimated_hours or 0.0) for t in completed_assigned_tasks)
            completed_actual = sum(float(t.actual_hours or 0.0) for t in completed_assigned_tasks)
            if completed_actual > 0.0:
                efficiency_score = round(min((completed_planned / completed_actual) * 100, 999.9), 1)
            else:
                efficiency_score = 100.0  # no actual hours logged = no overrun

            # Timesheet compliance
            submitted_days = submitted_days_map.get(emp.id, 0)
            timesheet_compliance_score = (submitted_days / working_days * 100) if working_days > 0 else 100.0

            rows.append(EmployeePerformanceRow(
                employee_id=emp.id,
                employee_code=emp.employee_code,
                employee_name=f"{emp.first_name} {emp.last_name or ''}".strip(),
                department_name=dept_name,
                team_name=team_name,
                utilization_percentage=round(utilization_pct, 1),
                planned_hours=round(planned_hours, 1),
                actual_hours=round(actual_hours, 1),
                variance_hours=round(variance_hours, 1),
                task_completion_percentage=round(task_completion_pct, 1),
                average_hours_per_task=round(average_hours_per_task, 1),
                average_delay_days=round(average_delay_days, 1),
                rework_hours=round(rework_hours, 1),
                productivity_score=round(productivity_score, 1),
                efficiency_score=round(efficiency_score, 1),
                timesheet_compliance_score=round(timesheet_compliance_score, 1),
                performance_rank=0
            ))

        def sort_key(row: EmployeePerformanceRow):
            return (
                0.4 * row.utilization_percentage + 
                0.3 * row.productivity_score + 
                0.2 * row.task_completion_percentage + 
                0.1 * row.timesheet_compliance_score
            )
        
        rows.sort(key=sort_key, reverse=True)
        for rank, row in enumerate(rows, 1):
            row.performance_rank = rank

        return rows
