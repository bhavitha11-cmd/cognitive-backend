from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.models.attendance import Attendance
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.employee_schedule import EmployeeSchedule
from app.services.dashboard.dashboard_common_service import DashboardCommonService
from app.services.productivity.kpi_calculator import KPICalculator
from app.services.productivity.policy_resolver import PolicyResolver
from app.schemas.dashboard_analytics import (
    TeamLeadSummary,
    TeamLeadCharts,
    TeamWorkloadPoint,
    TeamMemberAttendance
)

class TeamLeaderDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_leader_team_ids(self, employee_id: UUID) -> list[UUID]:
        """Get all team IDs led by the employee (role_in_team is LEAD or LEADER)."""
        stmt = (
            select(TeamMember.team_id)
            .where(
                TeamMember.employee_id == employee_id,
                TeamMember.role_in_team.in_(["LEAD", "LEADER", "TEAM_LEADER"])
            )
        )
        return list(self.db.scalars(stmt).all())

    def get_team_members(self, team_ids: list[UUID]) -> list[Employee]:
        if not team_ids:
            return []
        stmt = (
            select(Employee)
            .join(TeamMember, TeamMember.employee_id == Employee.id)
            .where(TeamMember.team_id.in_(team_ids), Employee.is_active == True)
        )
        return list(self.db.scalars(stmt).all())

    def get_summary(self, employee_id: UUID) -> TeamLeadSummary:
        team_ids = self.get_leader_team_ids(employee_id)
        if not team_ids:
            return TeamLeadSummary()

        members = self.get_team_members(team_ids)
        member_ids = [m.id for m in members]
        if not member_ids:
            return TeamLeadSummary()

        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 1. Total team members
        total_team_members = len(members)

        # 2. Today's attendance (PRESENT today)
        today_attendance_count = self.db.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.employee_id.in_(member_ids),
                Attendance.date == today,
                Attendance.status == "PRESENT"
            )
        ) or 0

        # 3. Pending approvals (time entries SUBMITTED)
        pending_approvals_count = self.db.scalar(
            select(func.count(TimeEntry.id)).where(
                TimeEntry.employee_id.in_(member_ids),
                TimeEntry.status == "SUBMITTED"
            )
        ) or 0

        # 4. Tasks in progress
        assigned_tasks_stmt = (
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id.in_(member_ids),
                Task.status == "IN_PROGRESS",
                Task.is_active == True
            )
        )
        tasks_in_progress_count = self.db.scalar(assigned_tasks_stmt) or 0

        # 5. Delayed tasks (planned delivery past today and not COMPLETED)
        delayed_tasks_stmt = (
            select(func.count(Task.id))
            .join(TaskAssignment, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id.in_(member_ids),
                Task.planned_delivery_date < today,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
                Task.is_active == True
            )
        )
        delayed_tasks_count = self.db.scalar(delayed_tasks_stmt) or 0

        # 6. Overloaded / Underutilized (Workload check for the current week)
        overloaded = 0
        underutilized = 0

        # Optimize capacity loops using batch queries
        # Batch query allocated hours
        allocated_hours_stmt = (
            select(TaskAssignment.employee_id, func.sum(Task.estimated_hours))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id.in_(member_ids),
                Task.planned_start_date <= end_of_week,
                Task.planned_end_date >= start_of_week,
                Task.is_active == True
            )
            .group_by(TaskAssignment.employee_id)
        )
        allocated_hours_map = {row[0]: float(row[1] or 0.0) for row in self.db.execute(allocated_hours_stmt).all()}

        # Batch query schedules
        working_days = DashboardCommonService.get_working_days_in_period(start_of_week, end_of_week, self.db)
        schedules_stmt = (
            select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
            .where(EmployeeSchedule.employee_id.in_(member_ids))
            .order_by(EmployeeSchedule.week_start_date.desc())
        )
        latest_schedules = {}
        for emp_id, avail in self.db.execute(schedules_stmt).all():
            if emp_id not in latest_schedules:
                latest_schedules[emp_id] = float(avail)

        for m in members:
            allocated_hours = allocated_hours_map.get(m.id, 0.0)
            weekly_hours = latest_schedules.get(m.id, 40.0)
            cap = working_days * (weekly_hours / 5.0)

            if cap > 0:
                load_pct = (allocated_hours / cap) * 100
                if load_pct > 120.0:
                    overloaded += 1
                elif load_pct < 50.0:
                    underutilized += 1

        return TeamLeadSummary(
            total_team_members=total_team_members,
            today_attendance_count=today_attendance_count,
            pending_approvals_count=pending_approvals_count,
            tasks_in_progress_count=tasks_in_progress_count,
            delayed_tasks_count=delayed_tasks_count,
            overloaded_employees_count=overloaded,
            underutilized_employees_count=underutilized
        )

    def get_charts(self, employee_id: UUID) -> TeamLeadCharts:
        team_ids = self.get_leader_team_ids(employee_id)
        if not team_ids:
            return TeamLeadCharts()

        members = self.get_team_members(team_ids)
        member_ids = [m.id for m in members]
        if not member_ids:
            return TeamLeadCharts()

        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        # 1. Employee Workload (This week)
        employee_workload = []
        # Batch query allocated hours
        allocated_hours_stmt = (
            select(TaskAssignment.employee_id, func.sum(Task.estimated_hours))
            .join(Task, TaskAssignment.task_id == Task.id)
            .where(
                TaskAssignment.employee_id.in_(member_ids),
                Task.planned_start_date <= end_of_week,
                Task.planned_end_date >= start_of_week,
                Task.is_active == True
            )
            .group_by(TaskAssignment.employee_id)
        )
        allocated_hours_map = {row[0]: float(row[1] or 0.0) for row in self.db.execute(allocated_hours_stmt).all()}

        # Batch query schedules
        working_days = DashboardCommonService.get_working_days_in_period(start_of_week, end_of_week, self.db)
        schedules_stmt = (
            select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
            .where(EmployeeSchedule.employee_id.in_(member_ids))
            .order_by(EmployeeSchedule.week_start_date.desc())
        )
        latest_schedules = {}
        for emp_id, avail in self.db.execute(schedules_stmt).all():
            if emp_id not in latest_schedules:
                latest_schedules[emp_id] = float(avail)

        for m in members:
            allocated = allocated_hours_map.get(m.id, 0.0)
            weekly_hours = latest_schedules.get(m.id, 40.0)
            cap = working_days * (weekly_hours / 5.0)
            pct = (allocated / cap * 100) if cap > 0 else 0.0
            employee_workload.append(TeamWorkloadPoint(
                employee_id=m.id,
                employee_name=f"{m.first_name} {m.last_name or ''}".strip(),
                assigned_hours=allocated,
                available_hours=cap,
                utilization_percentage=round(pct, 2)
            ))

        # 2. Employee Productivity today (using KPICalculator in batch)
        employee_productivity = []
        now_utc = datetime.now(timezone.utc)
        rule = PolicyResolver.get_rule(self.db)
        
        batch_raw_metrics = KPICalculator.calculate_raw_metrics_batch(self.db, member_ids, today, now_utc)
        for m in members:
            raw = batch_raw_metrics.get(m.id, {"presence_seconds": 0, "break_seconds": 0, "productive_seconds": 0})
            compiled = KPICalculator.compile_kpi_metrics(raw, rule)
            prod_pct = compiled.get("productivity_percentage", {}).get("percentage", 0.0)
            employee_productivity.append({
                "employeeName": f"{m.first_name} {m.last_name or ''}".strip(),
                "productivityPercentage": prod_pct
            })

        # 3. Weekly Task Completions (last 4 weeks)
        task_completions_weekly = []
        for i in range(4):
            w_start = start_of_week - timedelta(weeks=i)
            w_end = w_start + timedelta(days=6)
            completions = self.db.scalar(
                select(func.count(Task.id))
                .join(TaskAssignment, TaskAssignment.task_id == Task.id)
                .where(
                    TaskAssignment.employee_id.in_(member_ids),
                    Task.status == "COMPLETED",
                    Task.actual_delivery_date >= w_start,
                    Task.actual_delivery_date <= w_end,
                    Task.is_active == True
                )
            ) or 0
            task_completions_weekly.append({
                "weekLabel": f"W-{i}",
                "completedCount": completions
            })
        task_completions_weekly.reverse()

        # 4. Timesheet Compliance (Timesheets submitted vs expected for past 4 weeks)
        timesheet_compliance = []
        for i in range(4):
            w_start = start_of_week - timedelta(weeks=i)
            w_end = w_start + timedelta(days=6)
            
            # Count timesheets logged in this week range
            submitted = self.db.scalar(
                select(func.count(func.distinct(TimeEntry.employee_id)))
                .where(
                    TimeEntry.employee_id.in_(member_ids),
                    TimeEntry.date >= w_start,
                    TimeEntry.date <= w_end,
                    TimeEntry.status.in_(["SUBMITTED", "APPROVED"])
                )
            ) or 0
            compliance_pct = (submitted / len(members) * 100) if len(members) > 0 else 100.0
            timesheet_compliance.append({
                "weekLabel": f"W-{i}",
                "compliancePercentage": round(compliance_pct, 1)
            })
        timesheet_compliance.reverse()

        return TeamLeadCharts(
            employee_workload=employee_workload,
            employee_productivity=employee_productivity,
            task_completions_weekly=task_completions_weekly,
            timesheet_compliance=timesheet_compliance
        )

    def get_attendance(self, employee_id: UUID) -> list[TeamMemberAttendance]:
        team_ids = self.get_leader_team_ids(employee_id)
        if not team_ids:
            return []
        
        members = self.get_team_members(team_ids)
        member_ids = [m.id for m in members]
        if not members:
            return []
            
        today = date.today()
        # Batch query attendance for today
        attendance_stmt = select(Attendance).where(Attendance.employee_id.in_(member_ids), Attendance.date == today)
        attendance_map = {att.employee_id: att for att in self.db.scalars(attendance_stmt).all()}

        results = []
        for m in members:
            att = attendance_map.get(m.id)
            status = "ABSENT"
            clock_in = None
            clock_out = None
            if att:
                status = att.status
                clock_in = att.clock_in
                clock_out = att.clock_out
            results.append(TeamMemberAttendance(
                employee_id=m.id,
                employee_name=f"{m.first_name} {m.last_name or ''}".strip(),
                status=status,
                clock_in=clock_in,
                clock_out=clock_out
            ))
        return results
