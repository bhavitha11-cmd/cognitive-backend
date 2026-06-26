from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.project import Project
from app.models.task import Task
from app.models.calendar_event import CalendarEvent
from app.models.employee import Employee
from app.schemas.calendar import CalendarEventResponse
from app.core.rbac import get_user_context, DataAccessLevel


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
        type_set = set(types) if types else {
            "holiday", "birthday", "task", "project", "company_event"
        }
        events: list[CalendarEventResponse] = []

        if "holiday" in type_set:
            events.extend(self._get_holiday_events(from_date, to_date))
        if "birthday" in type_set:
            events.extend(self._get_birthday_events(from_date, to_date))
        if "task" in type_set:
            events.extend(self._get_task_events(from_date, to_date))
        if "project" in type_set:
            events.extend(self._get_project_events(from_date, to_date))
        if "company_event" in type_set:
            events.extend(self._get_company_events(from_date, to_date))

        events.sort(key=lambda e: e.start)
        return events

    def _get_holiday_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
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
                backgroundColor="#EF4444",
                borderColor="#EF4444",
                textColor="#ffffff",
                extendedProps={"type": "holiday", "holiday_type": h.holiday_type},
            )
            for h in holidays
        ]

    def _get_birthday_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
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
                        backgroundColor="#EC4899",
                        borderColor="#EC4899",
                        textColor="#ffffff",
                        extendedProps={"type": "birthday", "employee_name": emp.first_name},
                    )
                )
        return events

    def _get_task_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
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
            events.append(
                CalendarEventResponse(
                    id=f"task-{t.id}",
                    title=f"[{t.task_code}] {t.title[:40]}",
                    start=t.planned_delivery_date.isoformat(),
                    allDay=True,
                    backgroundColor=_STATUS_COLORS.get(t.status, "#6B7280"),
                    borderColor=_STATUS_COLORS.get(t.status, "#6B7280"),
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

    def _get_project_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
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
                        backgroundColor="#10B981",
                        borderColor="#10B981",
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
                        backgroundColor="#F59E0B",
                        borderColor="#F59E0B",
                        textColor="#ffffff",
                        extendedProps={
                            "type": "project_end",
                            "project_name": p.name,
                            "delayed": is_delayed,
                        },
                    )
                )
        return events

    def _get_company_events(self, from_date: date, to_date: date) -> list[CalendarEventResponse]:
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
                backgroundColor=e.color or "#8B5CF6",
                borderColor=e.color or "#8B5CF6",
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
