from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate, HolidayResponse, HolidayUpdate
from app.services.audit_service import AuditService
from app.services.calendar_service import CalendarService


class HolidayService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        year: int | None = None,
        holiday_type: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        sort_by: str = "date",
        sort_order: str = "asc",
    ) -> tuple[list[HolidayResponse], int]:
        stmt = select(Holiday)

        if year:
            stmt = stmt.where(sa_func.extract("year", Holiday.date) == year)
        if holiday_type:
            stmt = stmt.where(Holiday.holiday_type == holiday_type)
        if is_active is not None:
            stmt = stmt.where(Holiday.is_active == is_active)
        if search:
            stmt = stmt.where(Holiday.name.ilike(f"%{search}%"))
        if from_date:
            stmt = stmt.where(Holiday.date >= from_date)
        if to_date:
            stmt = stmt.where(Holiday.date <= to_date)

        count_stmt = select(sa_func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        sort_column = getattr(Holiday, sort_by, Holiday.date)
        if sort_order == "desc":
            sort_column = sort_column.desc()
        stmt = stmt.order_by(sort_column).offset(skip).limit(limit)

        holidays = self.db.scalars(stmt).all()
        return [HolidayResponse.model_validate(h) for h in holidays], total

    def get_by_id(self, id: uuid.UUID) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")
        return HolidayResponse.model_validate(holiday)

    def create(self, data: HolidayCreate) -> HolidayResponse:
        existing = self.db.scalar(
            select(Holiday).where(Holiday.date == data.date)
        )
        if existing:
            raise ValueError(
                f"A holiday already exists on {data.date}: '{existing.name}'"
            )

        holiday = Holiday(
            name=data.name,
            date=data.date,
            holiday_type=data.holiday_type,
            description=data.description,
            affects_working_days=data.affects_working_days if data.affects_working_days is not None else True,
            is_active=True,
            created_by=self.current_user_id,
        )
        self.db.add(holiday)
        self.db.commit()
        self.db.refresh(holiday)

        AuditService.log(
            self.db, "holiday", holiday.id, "CREATE",
            performed_by=self.current_user_id,
            new_value={
                "name": holiday.name,
                "date": str(holiday.date),
                "holiday_type": holiday.holiday_type,
                "affects_working_days": holiday.affects_working_days,
            },
        )

        if holiday.holiday_type != "EMERGENCY":
            CalendarService.trigger_holiday_recalculation(self.db, holiday.id, "CREATE")

        return HolidayResponse.model_validate(holiday)

    def update(self, id: uuid.UUID, data: HolidayUpdate) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        old_values = {
            "name": holiday.name,
            "date": str(holiday.date),
            "holiday_type": holiday.holiday_type,
            "is_active": holiday.is_active,
            "affects_working_days": holiday.affects_working_days,
        }

        update_data = data.model_dump(exclude_unset=True)

        if "date" in update_data and update_data["date"] != holiday.date:
            existing = self.db.scalar(
                select(Holiday).where(
                    Holiday.date == update_data["date"],
                    Holiday.id != id,
                )
            )
            if existing:
                raise ValueError(
                    f"A holiday already exists on {update_data['date']}: '{existing.name}'"
                )

        for field, value in update_data.items():
            setattr(holiday, field, value)

        holiday.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(holiday)

        new_values = {
            "name": holiday.name,
            "date": str(holiday.date),
            "holiday_type": holiday.holiday_type,
            "is_active": holiday.is_active,
            "affects_working_days": holiday.affects_working_days,
        }

        AuditService.log(
            self.db, "holiday", holiday.id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=new_values,
        )

        if "date" in update_data or "is_active" in update_data:
            CalendarService.trigger_holiday_recalculation(self.db, holiday.id, "UPDATE")

        return HolidayResponse.model_validate(holiday)

    def delete(self, id: uuid.UUID) -> None:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        old_values = {
            "name": holiday.name,
            "date": str(holiday.date),
        }

        holiday.is_active = False
        holiday.updated_by = self.current_user_id
        self.db.commit()

        AuditService.log(
            self.db, "holiday", holiday.id, "DELETE",
            performed_by=self.current_user_id,
            old_value=old_values,
        )

        CalendarService.trigger_holiday_recalculation(self.db, holiday.id, "DELETE")

    def toggle_active(self, id: uuid.UUID) -> HolidayResponse:
        holiday = self.db.get(Holiday, id)
        if not holiday:
            raise ValueError(f"Holiday with id {id} not found")

        holiday.is_active = not holiday.is_active
        holiday.updated_by = self.current_user_id
        self.db.commit()
        self.db.refresh(holiday)

        action = "ACTIVATE" if holiday.is_active else "DEACTIVATE"
        AuditService.log(
            self.db, "holiday", holiday.id, action,
            performed_by=self.current_user_id,
            new_value={"is_active": holiday.is_active},
        )

        CalendarService.trigger_holiday_recalculation(self.db, holiday.id, action)

        return HolidayResponse.model_validate(holiday)

    def get_upcoming(self, days: int = 30) -> list[HolidayResponse]:
        from datetime import timedelta
        today = date.today()
        end = today + timedelta(days=days)
        stmt = (
            select(Holiday)
            .where(
                Holiday.date >= today,
                Holiday.date <= end,
                Holiday.is_active == True,
            )
            .order_by(Holiday.date)
        )
        holidays = self.db.scalars(stmt).all()
        return [HolidayResponse.model_validate(h) for h in holidays]

    def check_date(self, check_date: date) -> HolidayResponse | None:
        holiday = self.db.scalar(
            select(Holiday).where(
                Holiday.date == check_date,
                Holiday.is_active == True,
            )
        )
        if holiday:
            return HolidayResponse.model_validate(holiday)
        return None

    def get_impact_analysis(self, holiday_id: uuid.UUID) -> dict:
        from app.models.project import Project
        from app.models.task import Task
        from app.services.working_day_engine import WorkingDayEngine
        from datetime import timedelta
        from sqlalchemy import func as sa_func

        holiday = self.db.get(Holiday, holiday_id)
        if not holiday:
            raise ValueError(f"Holiday with id {holiday_id} not found")

        holiday_date = holiday.date

        # Check if holiday falls on weekend/non-working day
        is_we = WorkingDayEngine.is_weekend(holiday_date, self.db)
        existing_other_holiday = self.db.scalar(
            select(Holiday.id).where(
                Holiday.date == holiday_date,
                Holiday.is_active == True,
                Holiday.id != holiday.id,
            )
        )
        is_already_holiday = existing_other_holiday is not None

        shift_days = 0 if (is_we or is_already_holiday) else 1

        active_projects = self.db.scalars(
            select(Project).where(
                Project.is_active == True,
                Project.status.notin_(["Completed", "Cancelled", "COMPLETED", "CANCELLED"]),
                Project.planned_start_date <= holiday_date,
                Project.planned_end_date >= holiday_date,
            )
        ).all()

        project_impacts = []
        affected_project_ids = []

        for proj in active_projects:
            proposed_start = proj.planned_start_date
            proposed_end = proj.planned_end_date

            if shift_days > 0 and proj.planned_end_date and proj.planned_end_date >= holiday_date:
                proposed_end = WorkingDayEngine.next_working_day(proj.planned_end_date + timedelta(days=1), self.db)

            tasks_count = self.db.scalar(
                select(sa_func.count(Task.id)).where(
                    Task.project_id == proj.id,
                    Task.is_active == True,
                    Task.status.notin_(["COMPLETED", "CANCELLED"]),
                    Task.planned_start_date <= holiday_date,
                    Task.planned_end_date >= holiday_date,
                )
            ) or 0

            risk = "LOW"
            if shift_days > 0:
                risk = "HIGH" if proj.priority == "HIGH" else "MEDIUM"

            project_impacts.append({
                "project_id": proj.id,
                "project_name": proj.name,
                "current_start_date": proj.planned_start_date,
                "current_end_date": proj.planned_end_date,
                "proposed_start_date": proposed_start,
                "proposed_end_date": proposed_end,
                "delivery_risk": risk,
                "affected_tasks_count": tasks_count,
            })
            affected_project_ids.append(proj.id)

        affected_tasks = []
        if affected_project_ids:
            tasks = self.db.scalars(
                select(Task).where(
                    Task.project_id.in_(affected_project_ids),
                    Task.is_active == True,
                    Task.status.notin_(["COMPLETED", "CANCELLED"]),
                    Task.planned_start_date <= holiday_date,
                    Task.planned_end_date >= holiday_date,
                )
            ).all()

            for task in tasks:
                proposed_start = task.planned_start_date
                proposed_end = task.planned_end_date

                if shift_days > 0:
                    if task.status == "IN_PROGRESS":
                        if task.planned_end_date and task.planned_end_date >= holiday_date:
                            proposed_end = WorkingDayEngine.next_working_day(task.planned_end_date + timedelta(days=1), self.db)
                    else:
                        if task.planned_start_date and task.planned_start_date >= holiday_date:
                            proposed_start = WorkingDayEngine.next_working_day(task.planned_start_date + timedelta(days=1), self.db)
                        if task.planned_end_date and task.planned_end_date >= holiday_date:
                            proposed_end = WorkingDayEngine.next_working_day(task.planned_end_date + timedelta(days=1), self.db)

                from app.models.task_assignment import TaskAssignment
                from app.models.employee import Employee
                assignee_stmt = (
                    select(Employee.first_name, Employee.last_name)
                    .join(TaskAssignment, TaskAssignment.employee_id == Employee.id)
                    .where(TaskAssignment.task_id == task.id, TaskAssignment.status != "CANCELLED")
                )
                assignee = self.db.execute(assignee_stmt).first()
                assignee_name = f"{assignee[0]} {assignee[1]}".strip() if assignee else None

                from app.models.task_dependency import TaskDependency
                dep_codes = self.db.scalars(
                    select(Task.task_code)
                    .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                    .where(TaskDependency.task_id == task.id)
                ).all()
                dep_info = f"Depends on: {', '.join(dep_codes)}" if dep_codes else None

                affected_tasks.append({
                    "task_id": task.id,
                    "task_name": task.title,
                    "assigned_employee_name": assignee_name,
                    "current_status": task.status,
                    "current_start_date": task.planned_start_date,
                    "current_end_date": task.planned_end_date,
                    "proposed_start_date": proposed_start,
                    "proposed_end_date": proposed_end,
                    "dependency_info": dep_info,
                })

        return {
            "holiday_id": holiday.id,
            "holiday_name": holiday.name,
            "holiday_date": holiday.date,
            "affected_projects": project_impacts,
            "affected_tasks": affected_tasks,
        }

    def apply_emergency_holiday(self, holiday_id: uuid.UUID, data) -> dict:
        from app.models.project import Project
        from app.models.task import Task
        from app.services.project_metrics_service import ProjectMetricsService
        from app.services.audit_service import AuditService
        from app.services.working_day_engine import WorkingDayEngine

        holiday = self.db.get(Holiday, holiday_id)
        if not holiday:
            raise ValueError(f"Holiday with id {holiday_id} not found")

        try:
            # 1. Validate Project Boundaries
            for t_update in data.task_updates:
                task = self.db.get(Task, t_update.task_id)
                if not task:
                    continue
                t_start = t_update.planned_start_date or task.planned_start_date
                t_end = t_update.planned_end_date or task.planned_end_date

                project = task.project
                p_override = next((p for p in data.project_updates if p.project_id == project.id), None)
                p_start = (p_override.planned_start_date if p_override else None) or project.planned_start_date
                p_end = (p_override.planned_end_date if p_override else None) or project.planned_end_date

                if t_start and p_start and t_start < p_start:
                    raise ValueError(f"Task {task.task_code} planned start date ({t_start}) cannot be before project planned start date ({p_start})")
                if t_end and p_end and t_end > p_end:
                    raise ValueError(f"Task {task.task_code} planned end date ({t_end}) cannot be after project planned end date ({p_end})")

            # 2. Validate Task Dependencies
            from app.models.task_dependency import TaskDependency
            for t_update in data.task_updates:
                task = self.db.get(Task, t_update.task_id)
                if not task:
                    continue
                t_start = t_update.planned_start_date or task.planned_start_date

                stmt = select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task.id)
                dep_ids = self.db.scalars(stmt).all()
                for dep_id in dep_ids:
                    dep_task = self.db.get(Task, dep_id)
                    if not dep_task:
                        continue
                    dep_override = next((t for t in data.task_updates if t.task_id == dep_id), None)
                    dep_end = (dep_override.planned_end_date if dep_override else None) or dep_task.planned_end_date

                    if t_start and dep_end and t_start < dep_end:
                        raise ValueError(f"Dependency violation: Task {task.task_code} starts on {t_start}, but depends on task {dep_task.task_code} which ends on {dep_end}")

            # 3. Validate Working Days & Final Schedule
            for t_update in data.task_updates:
                task = self.db.get(Task, t_update.task_id)
                if not task:
                    continue
                t_start = t_update.planned_start_date or task.planned_start_date
                t_end = t_update.planned_end_date or task.planned_end_date

                if t_start and t_end and t_start > t_end:
                    raise ValueError(f"Task {task.task_code} planned start date cannot be after its planned end date")

                if t_start and not WorkingDayEngine.is_working_day(t_start, self.db):
                    raise ValueError(f"Task {task.task_code} start date {t_start} must be a working day")
                if t_end and not WorkingDayEngine.is_working_day(t_end, self.db):
                    raise ValueError(f"Task {task.task_code} end date {t_end} must be a working day")

            # 4. Update Projects
            for p_update in data.project_updates:
                project = self.db.get(Project, p_update.project_id)
                if not project:
                    raise ValueError(f"Project with id {p_update.project_id} not found")

                old_val = {}
                new_val = {}

                if p_update.planned_start_date:
                    old_val["planned_start_date"] = project.planned_start_date.isoformat() if project.planned_start_date else None
                    project.planned_start_date = p_update.planned_start_date
                    new_val["planned_start_date"] = p_update.planned_start_date.isoformat()

                if p_update.planned_end_date:
                    old_val["planned_end_date"] = project.planned_end_date.isoformat() if project.planned_end_date else None
                    project.planned_end_date = p_update.planned_end_date
                    new_val["planned_end_date"] = p_update.planned_end_date.isoformat()

                if old_val:
                    AuditService.log(
                        self.db, "project", project.id, "EMERGENCY_HOLIDAY_SHIFT",
                        performed_by=self.current_user_id,
                        old_value=old_val,
                        new_value=new_val,
                    )

            # 5. Update Tasks
            for t_update in data.task_updates:
                task = self.db.get(Task, t_update.task_id)
                if not task:
                    raise ValueError(f"Task with id {t_update.task_id} not found")

                old_val = {}
                new_val = {}

                if t_update.planned_start_date:
                    old_val["planned_start_date"] = task.planned_start_date.isoformat() if task.planned_start_date else None
                    task.planned_start_date = t_update.planned_start_date
                    new_val["planned_start_date"] = t_update.planned_start_date.isoformat()

                if t_update.planned_end_date:
                    old_val["planned_end_date"] = task.planned_end_date.isoformat() if task.planned_end_date else None
                    task.planned_end_date = t_update.planned_end_date
                    new_val["planned_end_date"] = t_update.planned_end_date.isoformat()

                if old_val:
                    AuditService.log(
                        self.db, "task", task.id, "EMERGENCY_HOLIDAY_SHIFT",
                        performed_by=self.current_user_id,
                        old_value=old_val,
                        new_value=new_val,
                    )

            # 6. Recalculate Project Metrics
            unique_project_ids = set()
            for p_update in data.project_updates:
                unique_project_ids.add(p_update.project_id)
            for t_update in data.task_updates:
                task = self.db.get(Task, t_update.task_id)
                if task:
                    unique_project_ids.add(task.project_id)

            for pid in unique_project_ids:
                ProjectMetricsService.recalculate(self.db, pid)

            self.db.commit()
            return {"success": True, "message": "Emergency holiday shifts applied successfully"}
        except Exception as e:
            self.db.rollback()
            raise e

    def reject_emergency_holiday(self, holiday_id: uuid.UUID) -> dict:
        holiday = self.db.get(Holiday, holiday_id)
        if not holiday:
            raise ValueError(f"Holiday with id {holiday_id} not found")
        return {"success": True, "message": "Emergency holiday proposed shifts rejected. Schedules remain unchanged."}
