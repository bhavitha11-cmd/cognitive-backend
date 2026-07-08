from datetime import date, timedelta
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.employee_schedule import EmployeeSchedule
from app.models.holiday import Holiday

class DashboardCommonService:
    @staticmethod
    def get_working_days_in_period(start_date: date, end_date: date, db: Session) -> int:
        """Count working days (Monday-Friday) in period, excluding holidays."""
        current = start_date
        working_days = 0
        
        # Load holidays within the period to exclude
        holidays = set(
            db.scalars(
                select(Holiday.date).where(
                    Holiday.date >= start_date,
                    Holiday.date <= end_date,
                    Holiday.is_active == True
                )
            ).all()
        )
        
        while current <= end_date:
            # Weekend check (Saturday=5, Sunday=6)
            if current.weekday() < 5 and current not in holidays:
                working_days += 1
            current += timedelta(days=1)
        return working_days

    @staticmethod
    def get_expected_available_hours(employee_id: UUID, start_date: date, end_date: date, db: Session) -> float:
        """
        Calculate expected available hours for an employee during a date range.
        Reads from employee_schedules or defaults to 8 hours/day for working days.
        """
        # Retrieve weekly schedule
        weekly_hours = db.scalar(
            select(EmployeeSchedule.available_hours)
            .where(EmployeeSchedule.employee_id == employee_id)
            .order_by(EmployeeSchedule.week_start_date.desc())
            .limit(1)
        )
        if weekly_hours is None:
            weekly_hours = 40.0
        
        daily_rate = float(weekly_hours) / 5.0
        working_days = DashboardCommonService.get_working_days_in_period(start_date, end_date, db)
        return working_days * daily_rate

    @staticmethod
    def get_scoped_employee_ids(db: Session, user_ctx) -> list[UUID] | None:
        """
        Returns a list of employee IDs that the current user is allowed to see.
        Returns None if they have FULL access (can see everyone).
        """
        from app.core.rbac import DataAccessLevel
        if user_ctx.data_access_level == DataAccessLevel.FULL:
            return None

        from app.services.organization_hierarchy_service import OrganizationHierarchyService
        hierarchy_svc = OrganizationHierarchyService(db)
        subordinate_ids = hierarchy_svc.get_visible_employee_ids(user_ctx.employee_id)

        if user_ctx.data_access_level == DataAccessLevel.MANAGED:
            from app.models.project import Project
            from app.models.project_member import ProjectMember
            from app.models.task_assignment import TaskAssignment
            from app.models.task import Task

            # Projects managed/created by user or their subordinates
            project_ids_stmt = select(Project.id).where(
                (Project.project_manager_id.in_(subordinate_ids)) | (Project.created_by.in_(subordinate_ids))
            )
            project_ids = db.scalars(project_ids_stmt).all()

            emp_ids = set(subordinate_ids)
            if project_ids:
                # project members
                members_stmt = select(ProjectMember.employee_id).where(ProjectMember.project_id.in_(project_ids))
                emp_ids.update(db.scalars(members_stmt).all())

                # task assignments
                tasks_stmt = select(TaskAssignment.employee_id).join(Task).where(Task.project_id.in_(project_ids))
                emp_ids.update(db.scalars(tasks_stmt).all())

            return list(emp_ids)

        elif user_ctx.data_access_level == DataAccessLevel.TEAM:
            from app.models.team_member import TeamMember

            # Find teams led by user or subordinates
            team_ids_stmt = select(TeamMember.team_id).where(
                TeamMember.employee_id.in_(subordinate_ids),
                TeamMember.role_in_team.in_(["LEAD", "LEADER", "TEAM_LEADER"])
            )
            team_ids = db.scalars(team_ids_stmt).all()

            emp_ids = set(subordinate_ids)
            if team_ids:
                members_stmt = select(TeamMember.employee_id).where(TeamMember.team_id.in_(team_ids))
                emp_ids.update(db.scalars(members_stmt).all())

            return list(emp_ids)

        else:  # SELF
            return list(subordinate_ids)
