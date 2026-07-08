from datetime import date, datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session
from app.models.project import Project
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.models.attendance import Attendance
from app.models.department import Department
from app.models.task import Task
from app.models.audit_log import AuditLog
from app.models.employee_schedule import EmployeeSchedule
from app.models.project_member import ProjectMember
from app.models.task_assignment import TaskAssignment
from app.services.dashboard.dashboard_common_service import DashboardCommonService
from app.schemas.dashboard_analytics import (
    ExecutiveSummary,
    ExecutiveCharts,
    ProjectStatusCount,
    DepartmentPerf,
    BurnTrendPoint,
    EmployeeUtilPoint,
    ExecutiveAlerts,
    DashboardAlert,
    ExecutiveRecentActivities,
    RecentActivity,
    TeamPerformanceRow,
    ExecutiveTeamPerformanceResponse,
    ClientPerformanceRow,
    ExecutiveClientPerformanceResponse,
    ProjectListRow,
    ExecutiveProjectListResponse,
    TaskSummaryRow,
    ExecutiveTaskSummaryResponse,
    EmployeePerformanceRow
)


class ExecutiveDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def _get_scoped_project_ids(self, user_ctx) -> list[UUID] | None:
        from app.core.rbac import DataAccessLevel
        if not user_ctx or user_ctx.data_access_level == DataAccessLevel.FULL:
            return None

        from app.services.organization_hierarchy_service import OrganizationHierarchyService
        hierarchy_svc = OrganizationHierarchyService(self.db)
        subordinate_ids = hierarchy_svc.get_visible_employee_ids(user_ctx.employee_id)

        # Team assignments visibility: projects with active tasks assigned to user's or reports' teams
        from app.models.team_member import TeamMember
        user_team_ids_stmt = select(TeamMember.team_id).where(
            TeamMember.employee_id.in_(subordinate_ids),
            TeamMember.left_at.is_(None),
        )
        project_by_team_subq = (
            select(Task.project_id).distinct()
            .where(
                Task.team_id.in_(user_team_ids_stmt),
                Task.is_active == True,
            )
        )

        if user_ctx.data_access_level == DataAccessLevel.MANAGED:
            return list(self.db.scalars(
                select(Project.id).where(
                    (Project.project_manager_id.in_(subordinate_ids)) |
                    (Project.created_by.in_(subordinate_ids)) |
                    (Project.id.in_(project_by_team_subq))
                )
            ).all())
        elif user_ctx.data_access_level == DataAccessLevel.TEAM:
            member_project_subq = (
                select(ProjectMember.project_id)
                .where(
                    ProjectMember.employee_id.in_(subordinate_ids),
                    ProjectMember.left_at.is_(None),
                )
            )
            return list(self.db.scalars(
                select(Project.id).where(
                    (Project.project_manager_id.in_(subordinate_ids)) |
                    (Project.created_by.in_(subordinate_ids)) |
                    (Project.id.in_(member_project_subq)) |
                    (Project.id.in_(project_by_team_subq))
                )
            ).all())
        else:  # SELF
            member_project_subq = (
                select(ProjectMember.project_id)
                .where(
                    ProjectMember.employee_id.in_(subordinate_ids),
                    ProjectMember.left_at.is_(None),
                )
            )
            assigned_project_subq = (
                select(Task.project_id).distinct()
                .join(TaskAssignment, TaskAssignment.task_id == Task.id)
                .where(
                    TaskAssignment.employee_id.in_(subordinate_ids),
                    TaskAssignment.status != "CANCELLED",
                    Task.is_active == True,
                )
            )
            return list(self.db.scalars(
                select(Project.id).where(
                    (Project.project_manager_id.in_(subordinate_ids)) |
                    (Project.created_by.in_(subordinate_ids)) |
                    (Project.id.in_(member_project_subq)) |
                    (Project.id.in_(assigned_project_subq)) |
                    (Project.id.in_(project_by_team_subq))
                )
            ).all())

    def get_summary(self, from_date: date | None = None, to_date: date | None = None, user_ctx = None) -> ExecutiveSummary:
        today = date.today()
        if not from_date:
            from_date = today - timedelta(days=30)
        if not to_date:
            to_date = today

        scoped_project_ids = self._get_scoped_project_ids(user_ctx)
        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        # 1. Projects metrics
        projects_stmt = select(func.count(Project.id)).where(Project.is_active == True)
        if scoped_project_ids is not None:
            projects_stmt = projects_stmt.where(Project.id.in_(scoped_project_ids))
        total_projects = self.db.scalar(projects_stmt) or 0

        active_projects_stmt = select(func.count(Project.id)).where(Project.is_active == True, Project.status.in_(["In Progress", "On Hold"]))
        if scoped_project_ids is not None:
            active_projects_stmt = active_projects_stmt.where(Project.id.in_(scoped_project_ids))
        active_projects = self.db.scalar(active_projects_stmt) or 0

        completed_projects_stmt = select(func.count(Project.id)).where(Project.status == "Completed", Project.is_active == True)
        if scoped_project_ids is not None:
            completed_projects_stmt = completed_projects_stmt.where(Project.id.in_(scoped_project_ids))
        completed_projects = self.db.scalar(completed_projects_stmt) or 0

        delayed_projects_stmt = select(func.count(Project.id)).where(
            Project.is_active == True,
            Project.planned_end_date < today,
            Project.status.notin_(["Completed", "Cancelled"])
        )
        if scoped_project_ids is not None:
            delayed_projects_stmt = delayed_projects_stmt.where(Project.id.in_(scoped_project_ids))
        delayed_projects = self.db.scalar(delayed_projects_stmt) or 0

        # 2. Hours metrics
        planned_hours_stmt = select(func.coalesce(func.sum(Project.estimated_hours), 0.0))
        if scoped_project_ids is not None:
            planned_hours_stmt = planned_hours_stmt.where(Project.id.in_(scoped_project_ids))
        planned_hours = float(self.db.scalar(planned_hours_stmt) or 0.0)

        actual_hours_stmt = select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(TimeEntry.status != "REJECTED")
        if scoped_employee_ids is not None:
            actual_hours_stmt = actual_hours_stmt.where(TimeEntry.employee_id.in_(scoped_employee_ids))
        if scoped_project_ids is not None:
            actual_hours_stmt = actual_hours_stmt.where(TimeEntry.project_id.in_(scoped_project_ids))
        actual_hours = float(self.db.scalar(actual_hours_stmt) or 0.0)
        remaining_hours = max(0.0, planned_hours - actual_hours)

        # 3. Attendance
        attendance_stmt = select(func.count(Attendance.id)).where(Attendance.date == today, Attendance.status == "PRESENT")
        if scoped_employee_ids is not None:
            attendance_stmt = attendance_stmt.where(Attendance.employee_id.in_(scoped_employee_ids))
        employees_working_today = self.db.scalar(attendance_stmt) or 0

        # 4. Pending Timesheets
        pending_stmt = select(func.count(TimeEntry.id)).where(TimeEntry.status.in_(["DRAFT", "SUBMITTED"]))
        if scoped_employee_ids is not None:
            pending_stmt = pending_stmt.where(TimeEntry.employee_id.in_(scoped_employee_ids))
        pending_timesheets_count = self.db.scalar(pending_stmt) or 0

        # 5. Company Utilization
        active_emp_stmt = select(Employee).where(Employee.is_active == True)
        if scoped_employee_ids is not None:
            active_emp_stmt = active_emp_stmt.where(Employee.id.in_(scoped_employee_ids))
        active_employees = self.db.scalars(active_emp_stmt).all()
        active_employee_ids = [e.id for e in active_employees]

        total_logged_stmt = select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
            TimeEntry.date >= from_date,
            TimeEntry.date <= to_date,
            TimeEntry.status == "APPROVED"
        )
        if active_employee_ids:
            total_logged_stmt = total_logged_stmt.where(TimeEntry.employee_id.in_(active_employee_ids))
        else:
            total_logged_stmt = total_logged_stmt.where(TimeEntry.employee_id == None)
        total_logged = float(self.db.scalar(total_logged_stmt) or 0.0)

        # Optimize capacity calculation using 1 batch query for schedules
        total_capacity = 0.0
        if active_employee_ids:
            working_days = DashboardCommonService.get_working_days_in_period(from_date, to_date, self.db)
            latest_week_subq = (
                select(
                    EmployeeSchedule.employee_id,
                    func.max(EmployeeSchedule.week_start_date).label("latest_week"),
                )
                .where(EmployeeSchedule.employee_id.in_(active_employee_ids))
                .group_by(EmployeeSchedule.employee_id)
                .subquery()
            )
            schedules_stmt = (
                select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
                .join(
                    latest_week_subq,
                    and_(
                        EmployeeSchedule.employee_id == latest_week_subq.c.employee_id,
                        EmployeeSchedule.week_start_date == latest_week_subq.c.latest_week,
                    ),
                )
            )
            latest_schedules = {
                emp_id: float(avail)
                for emp_id, avail in self.db.execute(schedules_stmt).all()
            }

            for emp in active_employees:
                weekly_hours = latest_schedules.get(emp.id, 40.0)
                total_capacity += working_days * (weekly_hours / 5.0)

        company_utilization = (total_logged / total_capacity * 100) if total_capacity > 0.0 else 0.0

        return ExecutiveSummary(
            total_projects=total_projects,
            active_projects=active_projects,
            completed_projects=completed_projects,
            delayed_projects=delayed_projects,
            planned_hours=planned_hours,
            actual_hours=actual_hours,
            remaining_hours=remaining_hours,
            company_utilization_percentage=round(company_utilization, 2),
            employees_working_today=employees_working_today,
            pending_timesheets_count=pending_timesheets_count
        )

    def get_charts(self, from_date: date | None = None, to_date: date | None = None, user_ctx = None) -> ExecutiveCharts:
        today = date.today()
        if not from_date:
            from_date = today - timedelta(days=30)
        if not to_date:
            to_date = today

        scoped_project_ids = self._get_scoped_project_ids(user_ctx)
        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        # 1. Project Status Counts
        statuses_stmt = select(Project.status, func.count(Project.id)).where(Project.is_active == True)
        if scoped_project_ids is not None:
            statuses_stmt = statuses_stmt.where(Project.id.in_(scoped_project_ids))
        statuses_query = self.db.execute(statuses_stmt.group_by(Project.status)).all()
        project_statuses = [ProjectStatusCount(status=row[0], count=row[1]) for row in statuses_query]

        # 2. Department Performances
        depts_stmt = (
            select(Department.name, func.coalesce(func.sum(Project.estimated_hours), 0.0), func.coalesce(func.sum(Project.actual_hours), 0.0))
            .join(Project, Project.department_id == Department.id)
            .where(Project.is_active == True)
        )
        if scoped_project_ids is not None:
            depts_stmt = depts_stmt.where(Project.id.in_(scoped_project_ids))
        depts_query = self.db.execute(depts_stmt.group_by(Department.name)).all()
        
        dept_performances = []
        for row in depts_query:
            task_stmt = select(func.count(Task.id)).join(Project, Task.project_id == Project.id).join(Department, Project.department_id == Department.id).where(Department.name == row[0])
            if scoped_project_ids is not None:
                task_stmt = task_stmt.where(Project.id.in_(scoped_project_ids))
            task_count = self.db.scalar(task_stmt) or 0
            dept_performances.append(DepartmentPerf(
                department_name=row[0],
                estimated_hours=float(row[1]),
                actual_hours=float(row[2]),
                task_count=task_count
            ))

        # 3. Top 5 Overrun Projects (Planned vs Actual)
        overrun_stmt = select(Project).where(Project.is_active == True)
        if scoped_project_ids is not None:
            overrun_stmt = overrun_stmt.where(Project.id.in_(scoped_project_ids))
        overrun_query = self.db.scalars(
            overrun_stmt.order_by((Project.actual_hours - Project.estimated_hours).desc()).limit(5)
        ).all()
        planned_vs_actual = [
            {
                "projectName": p.name,
                "projectCode": p.project_code,
                "plannedHours": float(p.estimated_hours),
                "actualHours": float(p.actual_hours),
                "overrunHours": float(p.actual_hours - p.estimated_hours)
            }
            for p in overrun_query
        ]

        # 4. Hours Burn Trend (Daily Hours over past 30 days)
        burn_stmt = select(TimeEntry.date, func.sum(TimeEntry.hours_spent)).where(
            TimeEntry.date >= from_date,
            TimeEntry.date <= to_date,
            TimeEntry.status != "REJECTED"
        )
        if scoped_employee_ids is not None:
            burn_stmt = burn_stmt.where(TimeEntry.employee_id.in_(scoped_employee_ids))
        if scoped_project_ids is not None:
            burn_stmt = burn_stmt.where(TimeEntry.project_id.in_(scoped_project_ids))
        burn_query = self.db.execute(burn_stmt.group_by(TimeEntry.date).order_by(TimeEntry.date)).all()
        hours_burn_trend = [BurnTrendPoint(date=row[0], hours_logged=float(row[1])) for row in burn_query]

        # 5. Employee Utilization (Top 5 highly utilized)
        active_emp_stmt = select(Employee).where(Employee.is_active == True)
        if scoped_employee_ids is not None:
            active_emp_stmt = active_emp_stmt.where(Employee.id.in_(scoped_employee_ids))
        employees = self.db.scalars(active_emp_stmt).all()
        employee_ids = [emp.id for emp in employees]

        employee_utilization = []
        if employee_ids:
            # Batch Query actual hours
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

            # Batch Query schedules (one row per employee — the latest week)
            working_days = DashboardCommonService.get_working_days_in_period(from_date, to_date, self.db)
            charts_latest_week_subq = (
                select(
                    EmployeeSchedule.employee_id,
                    func.max(EmployeeSchedule.week_start_date).label("latest_week"),
                )
                .where(EmployeeSchedule.employee_id.in_(employee_ids))
                .group_by(EmployeeSchedule.employee_id)
                .subquery()
            )
            schedules_stmt = (
                select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
                .join(
                    charts_latest_week_subq,
                    and_(
                        EmployeeSchedule.employee_id == charts_latest_week_subq.c.employee_id,
                        EmployeeSchedule.week_start_date == charts_latest_week_subq.c.latest_week,
                    ),
                )
            )
            latest_schedules = {
                emp_id: float(avail)
                for emp_id, avail in self.db.execute(schedules_stmt).all()
            }

            for emp in employees:
                logged = actual_hours_map.get(emp.id, 0.0)
                weekly_hours = latest_schedules.get(emp.id, 40.0)
                cap = working_days * (weekly_hours / 5.0)
                pct = (logged / cap * 100) if cap > 0.0 else 0.0
                employee_utilization.append(EmployeeUtilPoint(
                    employee_id=emp.id,
                    employee_name=f"{emp.first_name} {emp.last_name or ''}".strip(),
                    utilization_percentage=round(pct, 2)
                ))
            employee_utilization.sort(key=lambda x: x.utilization_percentage, reverse=True)
            employee_utilization = employee_utilization[:5]

        return ExecutiveCharts(
            project_statuses=project_statuses,
            department_performances=dept_performances,
            planned_vs_actual=planned_vs_actual,
            hours_burn_trend=hours_burn_trend,
            employee_utilization=employee_utilization
        )

    def get_alerts(self, user_ctx = None) -> ExecutiveAlerts:
        today = date.today()
        alerts = []
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)
        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        # 1. Projects exceeding planned hours
        overrun_stmt = select(Project).where(Project.is_active == True, Project.actual_hours > Project.estimated_hours)
        if scoped_project_ids is not None:
            overrun_stmt = overrun_stmt.where(Project.id.in_(scoped_project_ids))
        overrun_projects = self.db.scalars(overrun_stmt.limit(5)).all()
        for p in overrun_projects:
            alerts.append(DashboardAlert(
                id=f"overrun-{p.id}",
                level="error",
                type="project_overrun",
                message=f"Project {p.project_code} ({p.name}) exceeded budget by {float(p.actual_hours - p.estimated_hours):.1f} hours.",
                reference_id=p.id
            ))

        # 2. Projects nearing delivery (within 14 days)
        nearing_stmt = select(Project).where(
            Project.is_active == True,
            Project.planned_end_date >= today,
            Project.planned_end_date <= today + timedelta(days=14),
            Project.status.notin_(["Completed", "Cancelled"])
        )
        if scoped_project_ids is not None:
            nearing_stmt = nearing_stmt.where(Project.id.in_(scoped_project_ids))
        nearing_projects = self.db.scalars(nearing_stmt.limit(5)).all()
        for p in nearing_projects:
            alerts.append(DashboardAlert(
                id=f"delivery-{p.id}",
                level="warning",
                type="project_delivery",
                message=f"Project {p.project_code} delivery is due on {p.planned_end_date.isoformat()}.",
                reference_id=p.id
            ))

        # 3. Employees with missing timesheets
        yesterday = today - timedelta(days=1)
        if yesterday.weekday() < 5:
            missing_stmt = select(Employee).where(
                Employee.is_active == True,
                ~Employee.id.in_(
                    select(TimeEntry.employee_id).where(TimeEntry.date == yesterday)
                ),
                ~Employee.id.in_(
                    select(Attendance.employee_id).where(Attendance.date == yesterday, Attendance.status == "LEAVE")
                )
            )
            if scoped_employee_ids is not None:
                missing_stmt = missing_stmt.where(Employee.id.in_(scoped_employee_ids))
            missing_timesheet_emps = self.db.scalars(missing_stmt.limit(5)).all()
            for emp in missing_timesheet_emps:
                alerts.append(DashboardAlert(
                    id=f"missing-ts-{emp.id}",
                    level="info",
                    type="timesheet_missing",
                    message=f"Employee {emp.first_name} {emp.last_name} has not submitted a timesheet for {yesterday.isoformat()}.",
                    reference_id=emp.id
                ))

        return ExecutiveAlerts(alerts=alerts)

    def get_recent_projects(self, user_ctx = None) -> list[Project]:
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)
        stmt = select(Project).where(Project.is_active == True)
        if scoped_project_ids is not None:
            stmt = stmt.where(Project.id.in_(scoped_project_ids))
        return self.db.scalars(stmt.order_by(Project.updated_at.desc()).limit(5)).all()

    def get_recent_activities(self, user_ctx = None) -> ExecutiveRecentActivities:
        from sqlalchemy import or_, and_
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)
        stmt = select(AuditLog).where(AuditLog.entity_type.in_(["project", "task"]))
        if scoped_project_ids is not None:
            scoped_task_ids = self.db.scalars(
                select(Task.id).where(Task.project_id.in_(scoped_project_ids))
            ).all()
            scope_filter = or_(
                and_(AuditLog.entity_type == 'project', AuditLog.entity_id.in_(scoped_project_ids)),
                and_(AuditLog.entity_type == 'task', AuditLog.entity_id.in_(scoped_task_ids)),
            )
            stmt = stmt.where(scope_filter)

        logs = self.db.scalars(stmt.order_by(AuditLog.performed_at.desc()).limit(10)).all()

        activities = []
        for l in logs:
            perf_by = "System"
            if l.performer:
                first = l.performer.first_name or ""
                last = l.performer.last_name or ""
                perf_by = f"{first} {last}".strip() or "System"

            activities.append(RecentActivity(
                id=l.id,
                action=l.action,
                performed_by_name=perf_by,
                entity_type=l.entity_type,
                entity_code=str(l.entity_id)[:8],
                timestamp=l.performed_at
            ))
        return ExecutiveRecentActivities(activities=activities)

    def get_team_performance(self, from_date: date | None = None, to_date: date | None = None, user_ctx = None) -> ExecutiveTeamPerformanceResponse:
        today = date.today()
        if not from_date:
            from_date = today - timedelta(days=30)
        if not to_date:
            to_date = today

        scoped_employee_ids = DashboardCommonService.get_scoped_employee_ids(self.db, user_ctx) if user_ctx else None

        from app.models.team import Team
        from app.models.team_member import TeamMember

        teams_stmt = select(Team).where(Team.is_active == True)
        if scoped_employee_ids is not None:
            teams_stmt = teams_stmt.join(TeamMember).where(TeamMember.employee_id.in_(scoped_employee_ids)).distinct()

        teams = self.db.scalars(teams_stmt).all()

        result = []
        for team in teams:
            mbr_stmt = select(TeamMember.employee_id).where(TeamMember.team_id == team.id, TeamMember.left_at.is_(None))
            if scoped_employee_ids is not None:
                mbr_stmt = mbr_stmt.where(TeamMember.employee_id.in_(scoped_employee_ids))
            team_emp_ids = list(self.db.scalars(mbr_stmt).all())
            headcount = len(team_emp_ids)

            act_hours = 0.0
            if team_emp_ids:
                act_hours = float(self.db.scalar(
                    select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0))
                    .where(
                        TimeEntry.employee_id.in_(team_emp_ids),
                        TimeEntry.date >= from_date,
                        TimeEntry.date <= to_date,
                        TimeEntry.status != "REJECTED"
                    )
                ) or 0.0)

            task_filter = [Task.team_id == team.id, Task.is_active == True]
            plan_hours = float(self.db.scalar(
                select(func.coalesce(func.sum(Task.estimated_hours), 0.0)).where(*task_filter)
            ) or 0.0)

            task_count = self.db.scalar(
                select(func.count(Task.id)).where(*task_filter)
            ) or 0

            overdue_tasks_count = self.db.scalar(
                select(func.count(Task.id)).where(
                    *task_filter,
                    Task.planned_delivery_date < today,
                    Task.status.notin_(["COMPLETED", "CANCELLED"])
                )
            ) or 0

            total_capacity = 0.0
            if team_emp_ids:
                working_days = DashboardCommonService.get_working_days_in_period(from_date, to_date, self.db)
                latest_week_subq = (
                    select(
                        EmployeeSchedule.employee_id,
                        func.max(EmployeeSchedule.week_start_date).label("latest_week"),
                    )
                    .where(EmployeeSchedule.employee_id.in_(team_emp_ids))
                    .group_by(EmployeeSchedule.employee_id)
                    .subquery()
                )
                schedules_stmt = (
                    select(EmployeeSchedule.employee_id, EmployeeSchedule.available_hours)
                    .join(
                        latest_week_subq,
                        and_(
                            EmployeeSchedule.employee_id == latest_week_subq.c.employee_id,
                            EmployeeSchedule.week_start_date == latest_week_subq.c.latest_week,
                        ),
                    )
                )
                latest_schedules = {
                    emp_id: float(avail)
                    for emp_id, avail in self.db.execute(schedules_stmt).all()
                }
                for emp_id in team_emp_ids:
                    weekly_hours = latest_schedules.get(emp_id, 40.0)
                    total_capacity += working_days * (weekly_hours / 5.0)

            utilization_pct = (act_hours / total_capacity * 100) if total_capacity > 0.0 else 0.0

            result.append(TeamPerformanceRow(
                team_id=team.id,
                team_name=team.team_name,
                department_name=team.department.name if team.department else None,
                headcount=headcount,
                utilization_percentage=round(utilization_pct, 2),
                planned_hours=plan_hours,
                actual_hours=act_hours,
                task_count=task_count,
                overdue_tasks_count=overdue_tasks_count
            ))

        return ExecutiveTeamPerformanceResponse(teams=result)

    def get_client_performance_exec(self, from_date: date | None = None, to_date: date | None = None, user_ctx = None) -> ExecutiveClientPerformanceResponse:
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)

        from app.models.client import Client

        clients = self.db.scalars(select(Client).where(Client.is_active == True).order_by(Client.name)).all()

        result = []
        for c in clients:
            proj_stmt = select(Project).where(Project.client_id == c.id, Project.is_active == True)
            if scoped_project_ids is not None:
                proj_stmt = proj_stmt.where(Project.id.in_(scoped_project_ids))
            projects = self.db.scalars(proj_stmt).all()
            if not projects and scoped_project_ids is not None:
                continue

            total = len(projects)
            active = sum(1 for p in projects if p.status in ("In Progress", "On Hold"))
            completed = sum(1 for p in projects if p.status == "Completed")

            delayed = 0
            for p in projects:
                if p.actual_end_date and p.planned_end_date:
                    if p.actual_end_date > p.planned_end_date:
                        delayed += 1
                elif p.planned_end_date and p.planned_end_date < date.today() and p.status not in ("Completed", "Cancelled"):
                    delayed += 1

            est = sum(float(p.estimated_hours or 0) for p in projects)

            p_ids = [p.id for p in projects]
            act = 0.0
            if p_ids:
                time_stmt = select(func.coalesce(func.sum(TimeEntry.hours_spent), 0.0)).where(
                    TimeEntry.project_id.in_(p_ids),
                    TimeEntry.status != "REJECTED"
                )
                if from_date:
                    time_stmt = time_stmt.where(TimeEntry.date >= from_date)
                if to_date:
                    time_stmt = time_stmt.where(TimeEntry.date <= to_date)
                act = float(self.db.scalar(time_stmt) or 0.0)

            on_time_pct = round(((completed - delayed) / completed * 100) if completed > 0 else 100.0, 1)

            result.append(ClientPerformanceRow(
                client_id=c.id,
                client_name=c.name,
                total_projects=total,
                active_projects=active,
                completed_projects=completed,
                delayed_projects=delayed,
                planned_hours=est,
                actual_hours=act,
                on_time_delivery_pct=on_time_pct
            ))

        return ExecutiveClientPerformanceResponse(clients=result)

    def get_individual_performance(
        self,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        user_ctx = None
    ) -> list[EmployeePerformanceRow]:
        from app.services.dashboard.employee_performance_service import EmployeePerformanceService
        perf_svc = EmployeePerformanceService(self.db)
        return perf_svc.get_rankings(department_id, team_id, from_date, to_date, user_ctx)

    def get_project_list(
        self,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        user_ctx = None
    ) -> ExecutiveProjectListResponse:
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)

        proj_stmt = select(Project).where(Project.is_active == True)
        if scoped_project_ids is not None:
            proj_stmt = proj_stmt.where(Project.id.in_(scoped_project_ids))
        if department_id:
            proj_stmt = proj_stmt.where(Project.department_id == department_id)
        if team_id:
            team_project_subq = select(Task.project_id).where(Task.team_id == team_id, Task.is_active == True).distinct()
            proj_stmt = proj_stmt.where(Project.id.in_(team_project_subq))

        projects = self.db.scalars(proj_stmt).all()
        project_ids = [p.id for p in projects]

        if not project_ids:
            return ExecutiveProjectListResponse(projects=[])

        time_stmt = select(TimeEntry.project_id, func.sum(TimeEntry.hours_spent)).where(
            TimeEntry.project_id.in_(project_ids),
            TimeEntry.status != "REJECTED"
        )
        if from_date:
            time_stmt = time_stmt.where(TimeEntry.date >= from_date)
        if to_date:
            time_stmt = time_stmt.where(TimeEntry.date <= to_date)

        hours_by_project = {row[0]: float(row[1] or 0.0) for row in self.db.execute(time_stmt.group_by(TimeEntry.project_id)).all()}

        from sqlalchemy import case
        task_counts_stmt = (
            select(
                Task.project_id,
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == "COMPLETED", 1), else_=0)).label("completed")
            )
            .where(Task.is_active == True)
            .group_by(Task.project_id)
        )
        task_counts_data = {row[0]: (row[1], row[2] or 0) for row in self.db.execute(task_counts_stmt).all()}

        result = []
        for p in projects:
            actual = hours_by_project.get(p.id, 0.0)
            est = float(p.estimated_hours or 0.0)
            overrun = round(actual - est, 2)
            overrun_pct = round((overrun / est * 100) if est > 0.0 else 0.0, 1)

            tc, ctc = task_counts_data.get(p.id, (0, 0))

            pm_name = None
            if p.project_manager:
                pm_name = f"{p.project_manager.first_name} {p.project_manager.last_name or ''}".strip()

            result.append(ProjectListRow(
                project_id=p.id,
                project_code=p.project_code,
                project_name=p.name,
                client_name=p.client.name if p.client else None,
                department_name=p.department.name if p.department else None,
                project_manager_name=pm_name,
                planned_hours=est,
                actual_hours=actual,
                overrun_hours=overrun,
                overrun_percentage=overrun_pct,
                status=p.status,
                task_count=tc,
                completed_task_count=ctc,
                planned_end_date=p.planned_end_date
            ))

        result.sort(key=lambda x: x.overrun_hours, reverse=True)
        return ExecutiveProjectListResponse(projects=result)

    def get_task_summary(
        self,
        department_id: UUID | None = None,
        team_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        user_ctx = None
    ) -> ExecutiveTaskSummaryResponse:
        scoped_project_ids = self._get_scoped_project_ids(user_ctx)

        stmt = select(Task, Project.name.label("project_name")).join(Project, Task.project_id == Project.id).where(Task.is_active == True)
        if scoped_project_ids is not None:
            stmt = stmt.where(Task.project_id.in_(scoped_project_ids))
        if department_id:
            stmt = stmt.where(Project.department_id == department_id)
        if team_id:
            stmt = stmt.where(Task.team_id == team_id)

        tasks_result = self.db.execute(stmt).all()
        task_ids = [row[0].id for row in tasks_result]

        if not task_ids:
            return ExecutiveTaskSummaryResponse(tasks=[])

        time_stmt = select(TimeEntry.task_id, func.sum(TimeEntry.hours_spent)).where(
            TimeEntry.task_id.in_(task_ids),
            TimeEntry.status != "REJECTED"
        )
        if from_date:
            time_stmt = time_stmt.where(TimeEntry.date >= from_date)
        if to_date:
            time_stmt = time_stmt.where(TimeEntry.date <= to_date)

        hours_by_task = {row[0]: float(row[1] or 0.0) for row in self.db.execute(time_stmt.group_by(TimeEntry.task_id)).all()}

        assignee_map = {}
        assignee_rows = self.db.execute(
            select(TaskAssignment.task_id, Employee.first_name, Employee.last_name)
            .join(Employee, TaskAssignment.employee_id == Employee.id)
            .where(TaskAssignment.task_id.in_(task_ids))
            .distinct(TaskAssignment.task_id)
        ).all()
        for a_row in assignee_rows:
            assignee_map[a_row[0]] = f"{a_row[1]} {a_row[2] or ''}".strip()

        result = []
        for row in tasks_result:
            t = row[0]
            actual = hours_by_task.get(t.id, 0.0)
            est = float(t.estimated_hours or 0.0)
            overrun = round(actual - est, 2)

            result.append(TaskSummaryRow(
                task_id=t.id,
                task_code=t.task_code,
                title=t.title,
                project_name=row[1],
                assignee_name=assignee_map.get(t.id),
                status=t.status,
                priority=t.priority,
                estimated_hours=est,
                actual_hours=actual,
                overrun_hours=overrun,
                planned_delivery_date=t.planned_delivery_date
            ))

        result.sort(key=lambda x: x.overrun_hours, reverse=True)
        return ExecutiveTaskSummaryResponse(tasks=result)


