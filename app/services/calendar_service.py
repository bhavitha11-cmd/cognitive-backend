from __future__ import annotations

import uuid
from datetime import date, timedelta
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.project import Project
from app.models.task import Task
from app.models.calendar_event import CalendarEvent
from app.models.employee import Employee
from app.models.calendar_settings import CalendarSettings
from app.schemas.calendar import CalendarEventResponse
from app.core.rbac import get_user_context, DataAccessLevel

logger = logging.getLogger("uvicorn.error")

_STATUS_COLORS: dict[str, str] = {
    "NOT_STARTED": "#6B7280",
    "IN_PROGRESS": "#3B82F6",
    "ON_HOLD": "#F59E0B",
    "COMPLETED": "#10B981",
    "CANCELLED": "#EF4444",
}


class CalendarService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    def get_events(
        self,
        from_date: date,
        to_date: date,
        types: list[str] | None = None,
    ) -> list[CalendarEventResponse]:
        settings = self.db.scalar(select(CalendarSettings))
        if not settings:
            settings = CalendarSettings(
                enable_birthdays=True,
                enable_company_events=True,
                enable_holidays=True,
                enable_task_events=True,
                enable_project_events=True,
                color_holiday="#EF4444",
                color_birthday="#EC4899",
                color_task="#3B82F6",
                color_project="#10B981",
                color_company_event="#8B5CF6",
            )

        type_set = set(types) if types else {
            "holiday", "birthday", "task", "project", "company_event", "leave", "task_risk", "paused_task"
        }
        events: list[CalendarEventResponse] = []

        if "holiday" in type_set and settings.enable_holidays:
            events.extend(self._get_holiday_events(from_date, to_date, settings.color_holiday))
        if "birthday" in type_set and settings.enable_birthdays:
            events.extend(self._get_birthday_events(from_date, to_date, settings.color_birthday))
        if "task" in type_set and settings.enable_task_events:
            events.extend(self._get_task_events(from_date, to_date, settings.color_task))
        if "project" in type_set and settings.enable_project_events:
            events.extend(self._get_project_events(from_date, to_date, settings.color_project))
        if "company_event" in type_set and settings.enable_company_events:
            events.extend(self._get_company_events(from_date, to_date, settings.color_company_event))
        if "leave" in type_set:
            events.extend(self._get_leave_events(from_date, to_date))
        if "task_risk" in type_set:
            events.extend(self._get_task_risk_events(from_date, to_date))
        if "paused_task" in type_set:
            events.extend(self._get_paused_task_events(from_date, to_date))

        events.sort(key=lambda e: e.start)
        return events

    def _get_holiday_events(self, from_date: date, to_date: date, color: str) -> list[CalendarEventResponse]:
        holidays = self.db.scalars(
            select(Holiday).where(
                Holiday.date.between(from_date, to_date),
                Holiday.is_active == True,
            )
        ).all()
        return [
            CalendarEventResponse(
                id=f"holiday-{h.id}",
                title=h.name,
                start=h.date.isoformat(),
                allDay=True,
                backgroundColor=color,
                borderColor=color,
                textColor="#ffffff",
                extendedProps={"type": "holiday", "holiday_type": h.holiday_type},
            )
            for h in holidays
        ]

    def _get_birthday_events(self, from_date: date, to_date: date, color: str) -> list[CalendarEventResponse]:
        employees = self.db.scalars(
            select(Employee).where(
                Employee.is_active == True,
                Employee.date_of_birth.isnot(None),
            )
        ).all()

        events: list[CalendarEventResponse] = []
        for emp in employees:
            if not emp.date_of_birth:
                continue
            try:
                bday_this_year = date(from_date.year, emp.date_of_birth.month, emp.date_of_birth.day)
            except ValueError:
                bday_this_year = date(from_date.year, 3, 1)

            if from_date <= bday_this_year <= to_date:
                events.append(
                    CalendarEventResponse(
                        id=f"bday-{emp.id}",
                        title=f"{emp.first_name}'s Birthday",
                        start=bday_this_year.isoformat(),
                        allDay=True,
                        backgroundColor=color,
                        borderColor=color,
                        textColor="#ffffff",
                        extendedProps={"type": "birthday", "employee_name": emp.first_name},
                    )
                )
        return events

    def _get_task_events(self, from_date: date, to_date: date, color: str) -> list[CalendarEventResponse]:
        tasks = self.db.scalars(
            select(Task).where(
                Task.planned_delivery_date.between(from_date, to_date),
                Task.is_active == True,
                Task.status.notin_(["COMPLETED", "CANCELLED"]),
            )
        ).all()

        if self.current_user_id:
            tasks = [t for t in tasks if self._is_task_visible(t)]

        events: list[CalendarEventResponse] = []
        for t in tasks:
            if not t.planned_delivery_date:
                continue
            is_overdue = t.planned_delivery_date < date.today()
            task_color = color or _STATUS_COLORS.get(t.status, "#6B7280")
            events.append(
                CalendarEventResponse(
                    id=f"task-{t.id}",
                    title=f"[{t.task_code}] {t.title[:40]}",
                    start=t.planned_delivery_date.isoformat(),
                    allDay=True,
                    backgroundColor=task_color,
                    borderColor=task_color,
                    textColor="#ffffff",
                    extendedProps={
                        "type": "task",
                        "status": t.status,
                        "task_code": t.task_code,
                        "overdue": is_overdue,
                    },
                )
            )
        return events

    def _get_project_events(self, from_date: date, to_date: date, color: str) -> list[CalendarEventResponse]:
        projects = self.db.scalars(
            select(Project).where(
                Project.is_active == True,
                Project.status.notin_(["Completed", "Cancelled"]),
            )
        ).all()

        if self.current_user_id:
            projects = [p for p in projects if self._is_project_visible(p)]

        events: list[CalendarEventResponse] = []
        for p in projects:
            if p.planned_start_date and from_date <= p.planned_start_date <= to_date:
                events.append(
                    CalendarEventResponse(
                        id=f"project-start-{p.id}",
                        title=f"[Start] {p.name[:40]}",
                        start=p.planned_start_date.isoformat(),
                        allDay=True,
                        backgroundColor=color,
                        borderColor=color,
                        textColor="#ffffff",
                        extendedProps={"type": "project_start", "project_name": p.name},
                    )
                )
            if p.planned_end_date and from_date <= p.planned_end_date <= to_date:
                is_delayed = p.planned_end_date < date.today() and p.status != "Completed"
                events.append(
                    CalendarEventResponse(
                        id=f"project-end-{p.id}",
                        title=f"[Due] {p.name[:40]}",
                        start=p.planned_end_date.isoformat(),
                        allDay=True,
                        backgroundColor=color,
                        borderColor=color,
                        textColor="#ffffff",
                        extendedProps={
                            "type": "project_end",
                            "project_name": p.name,
                            "delayed": is_delayed,
                        },
                    )
                )
        return events

    def _get_company_events(self, from_date: date, to_date: date, default_color: str) -> list[CalendarEventResponse]:
        events = self.db.scalars(
            select(CalendarEvent).where(
                CalendarEvent.event_type == "COMPANY_EVENT",
                CalendarEvent.is_active == True,
                CalendarEvent.start_date.between(from_date, to_date),
            )
        ).all()
        return [
            CalendarEventResponse(
                id=f"company-{e.id}",
                title=e.title,
                start=e.start_date.isoformat(),
                end=e.end_date.isoformat() if e.end_date else None,
                allDay=e.is_all_day,
                backgroundColor=e.color or default_color,
                borderColor=e.color or default_color,
                textColor=e.text_color or "#ffffff",
                extendedProps={"type": "company_event", "event_subtype": e.event_subtype},
            )
            for e in events
        ]

    def _is_task_visible(self, task: Task) -> bool:
        if not self.current_user_id:
            return True
        user_ctx = get_user_context(self.db, str(self.current_user_id))
        if user_ctx.data_access_level >= DataAccessLevel.MANAGED:
            return True
        for assignment in task.assignments:
            if assignment.employee_id == self.current_user_id:
                return True
        return False

    def _is_project_visible(self, project: Project) -> bool:
        if not self.current_user_id:
            return True
        user_ctx = get_user_context(self.db, str(self.current_user_id))
        if user_ctx.data_access_level >= DataAccessLevel.MANAGED:
            return True
        if project.project_manager_id == self.current_user_id:
            return True
        for member in project.members:
            if member.employee_id == self.current_user_id:
                return True
        return False

    @classmethod
    def trigger_holiday_recalculation(cls, db: Session, holiday_id: uuid.UUID, action: str) -> dict:
        holiday = db.get(Holiday, holiday_id)
        if not holiday:
            return {"error": f"Holiday {holiday_id} not found"}

        if getattr(holiday, "holiday_type", None) == "EMERGENCY":
            return {"message": "Emergency holiday - skipping auto recalculation"}

        holiday_date = holiday.date
        action_lower = action.lower()

        is_addition = action_lower in ("create", "activate")
        is_removal = action_lower in ("delete", "deactivate")
        if not is_addition and not is_removal and action_lower != "update":
            return {"message": f"No action needed for: {action}"}

        from app.services.working_day_engine import WorkingDayEngine
        if WorkingDayEngine.is_weekend(holiday_date, db):
            logger.info(
                f"[Recalc] Holiday '{holiday.name}' on {holiday_date} is a weekend — skipping"
            )
            return {"message": "Holiday falls on weekend, no recalculation needed"}

        # Identify affected projects
        project_ids = db.scalars(
            select(Project.id).where(
                Project.is_active == True,
                Project.planned_start_date <= holiday_date,
                Project.planned_end_date >= holiday_date,
            )
        ).all()

        # Identify affected tasks
        task_ids = []
        if project_ids:
            task_ids = db.scalars(
                select(Task.id).where(
                    Task.project_id.in_(project_ids),
                    Task.is_active == True,
                    Task.status.notin_(["COMPLETED", "CANCELLED"]),
                    Task.planned_start_date <= holiday_date,
                    Task.planned_end_date >= holiday_date,
                )
            ).all()

        results = {
            "holiday_id": str(holiday_id),
            "action": action,
            "affected_projects": len(project_ids),
            "affected_tasks": len(task_ids),
            "project_adjustments": [],
            "task_adjustments": [],
        }

        from app.services.audit_service import AuditService
        from app.services.project_metrics_service import ProjectMetricsService

        # Recalculate projects — accumulate all changes, commit once at the end
        # so the whole recalculation is atomic. Audit is logged before the
        # single commit below.
        adjusted_project_ids: list[uuid.UUID] = []
        for pid in project_ids:
            proj = db.get(Project, pid)
            if proj and proj.planned_end_date:
                current_end = proj.planned_end_date
                direction = 1 if is_addition else -1
                candidate = current_end + timedelta(days=direction)
                while not WorkingDayEngine.is_working_day(candidate, db):
                    candidate += timedelta(days=direction)

                if candidate != current_end:
                    proj.planned_end_date = candidate
                    adjusted_project_ids.append(pid)
                    AuditService.log(
                        db, "project", pid, "AUTO_RECALC",
                        old_value={"planned_end_date": current_end.isoformat()},
                        new_value={"planned_end_date": candidate.isoformat()},
                    )
                    results["project_adjustments"].append({
                        "project_id": str(pid),
                        "old_end": current_end.isoformat(),
                        "new_end": candidate.isoformat()
                    })

        # Recalculate tasks — accumulate, commit once at the end.
        for tid in task_ids:
            task = db.get(Task, tid)
            if task and task.planned_end_date:
                current_end = task.planned_end_date
                direction = 1 if is_addition else -1
                candidate = current_end + timedelta(days=direction)
                while not WorkingDayEngine.is_working_day(candidate, db):
                    candidate += timedelta(days=direction)

                if candidate != current_end:
                    task.planned_end_date = candidate
                    results["task_adjustments"].append({
                        "task_id": str(tid),
                        "old_end": current_end.isoformat(),
                        "new_end": candidate.isoformat()
                    })

        # Single atomic commit for all project/task adjustments + their audits.
        if results["project_adjustments"] or results["task_adjustments"]:
            try:
                db.flush()
                # Metrics recalc must run before the commit so it is part of the
                # same atomic transaction.
                for pid in adjusted_project_ids:
                    ProjectMetricsService.recalculate(db, pid)
                db.commit()
            except Exception:
                db.rollback()
                raise

        if project_ids or task_ids:
            logger.info(
                f"[Recalc] Holiday '{holiday.name}' ({action}): "
                f"{len(project_ids)} projects, {len(task_ids)} tasks adjusted"
            )

        return results

    def _can_see_all(self) -> bool:
        """True when the current user's data-access level is MANAGED or higher.

        Mirrors the visibility gate used by _is_task_visible / _is_project_visible.
        When there is no current user (system context) we do not restrict.
        """
        if not self.current_user_id:
            return True
        user_ctx = get_user_context(self.db, str(self.current_user_id))
        return user_ctx.data_access_level >= DataAccessLevel.MANAGED

    def _get_leave_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
        from app.models.leave_request import LeaveRequest
        from sqlalchemy.orm import joinedload
        stmt = (
            select(LeaveRequest)
            .options(joinedload(LeaveRequest.employee))
            .where(
                LeaveRequest.status == "APPROVED",
                LeaveRequest.from_date <= to_date,
                LeaveRequest.to_date >= from_date,
            )
        )
        # Data-access scoping: below MANAGED, a user only sees their own leave.
        if self.current_user_id and not self._can_see_all():
            stmt = stmt.where(LeaveRequest.employee_id == self.current_user_id)
        leaves = self.db.scalars(stmt).all()
        return [
            CalendarEventResponse(
                id=f"leave-{l.id}",
                title=f"[Leave] {l.employee.first_name} {l.employee.last_name or ''}".strip(),
                start=l.from_date.isoformat(),
                end=(l.to_date + timedelta(days=1)).isoformat(),
                allDay=True,
                backgroundColor="#EC4899",
                borderColor="#EC4899",
                textColor="#ffffff",
                extendedProps={
                    "type": "leave",
                    "employee_name": f"{l.employee.first_name} {l.employee.last_name or ''}".strip(),
                },
            )
            for l in leaves
        ]

    def _get_task_risk_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
        from app.models.task_continuity import TaskRisk
        from sqlalchemy.orm import joinedload
        risks = self.db.scalars(
            select(TaskRisk)
            .options(joinedload(TaskRisk.task))
            .where(
                TaskRisk.status == "PENDING_MANAGER_ACTION",
                TaskRisk.leave_start_date <= to_date,
                TaskRisk.leave_end_date >= from_date,
            )
        ).all()
        # Data-access scoping: only show risks on tasks the user can see.
        if self.current_user_id:
            risks = [r for r in risks if r.task and self._is_task_visible(r.task)]
        return [
            CalendarEventResponse(
                id=f"risk-{r.id}",
                title=f"[Risk] {r.task.task_code}: {r.task.title[:30]}",
                start=r.leave_start_date.isoformat(),
                end=(r.leave_end_date + timedelta(days=1)).isoformat(),
                allDay=True,
                backgroundColor="#EF4444",
                borderColor="#EF4444",
                textColor="#ffffff",
                extendedProps={
                    "type": "task_risk",
                    "task_id": str(r.task_id),
                    "risk_level": r.risk_level,
                },
            )
            for r in risks
        ]

    def _get_paused_task_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
        from app.models.task_continuity import TaskPauseHistory
        from sqlalchemy.orm import joinedload
        pauses = self.db.scalars(
            select(TaskPauseHistory)
            .options(joinedload(TaskPauseHistory.task))
            .where(
                TaskPauseHistory.is_active == True,
            )
        ).all()
        # Data-access scoping: only show pauses on tasks the user can see.
        if self.current_user_id:
            pauses = [p for p in pauses if p.task and self._is_task_visible(p.task)]
        events = []
        for p in pauses:
            paused_d = p.paused_at.date()
            resumed_d = p.resumed_at.date() if p.resumed_at else date.today()
            if paused_d <= to_date and resumed_d >= from_date:
                events.append(
                    CalendarEventResponse(
                        id=f"paused-{p.id}",
                        title=f"[Paused] {p.task.task_code}: {p.task.title[:30]}",
                        start=paused_d.isoformat(),
                        end=(resumed_d + timedelta(days=1)).isoformat(),
                        allDay=True,
                        backgroundColor="#F59E0B",
                        borderColor="#F59E0B",
                        textColor="#ffffff",
                        extendedProps={
                            "type": "paused_task",
                            "task_id": str(p.task_id),
                        },
                    )
                )
        return events
