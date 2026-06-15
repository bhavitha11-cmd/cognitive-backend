import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.time_entry import TimeEntry
from app.schemas.time_entry import (
    TimeEntryCreate,
    TimeEntryResponse,
    TimeEntryUpdate,
    TimesheetSummary,
)
from app.services.audit_service import AuditService


class TimeEntryService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        employee_id: UUID | None = None,
        task_id: UUID | None = None,
        project_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
    ) -> tuple[list[TimeEntryResponse], int]:
        base_q = (
            select(TimeEntry)
            .options(
                joinedload(TimeEntry.employee),
                joinedload(TimeEntry.task),
                joinedload(TimeEntry.project),
                joinedload(TimeEntry.approver),
            )
        )
        count_q = select(func.count()).select_from(TimeEntry)

        filters = self._build_filters(employee_id, task_id, project_id, date_from, date_to, status)
        for f in filters:
            base_q = base_q.where(f)
            count_q = count_q.where(f)

        total = self.db.scalar(count_q) or 0
        entries = self.db.scalars(
            base_q.order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).unique().all()

        return [self._build_response(e) for e in entries], total

    def get_by_id(self, id: UUID) -> TimeEntryResponse:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")
        return self._build_response(entry)

    # ── Create ─────────────────────────────────────────────────────────────────

    def create(self, data: TimeEntryCreate) -> TimeEntryResponse:
        # Resolve employee_id — only allow creating entries for yourself
        employee_id = data.employee_id if data.employee_id else self.current_user_id
        if not employee_id:
            raise ValueError("employee_id is required")
        if employee_id != self.current_user_id:
            raise ValueError("You can only create time entries for yourself")

        # Validate employee exists
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee with id {employee_id} not found")

        # Validate task exists
        task = self.db.get(Task, data.task_id)
        if not task:
            raise ValueError(f"Task with id {data.task_id} not found")
        if not task.is_active:
            raise ValueError("Cannot log time against an inactive task")

        # project_id is denormalized from the task
        project_id = task.project_id

        # Validate project exists
        project = self.db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")

        # Warn on duplicate (same employee + task + date) — allowed but noted
        duplicate_exists = self.db.scalar(
            select(func.count()).select_from(TimeEntry).where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.task_id == data.task_id,
                TimeEntry.date == data.date,
            )
        ) or 0

        entry = TimeEntry(
            employee_id=employee_id,
            task_id=data.task_id,
            project_id=project_id,
            date=data.date,
            hours_spent=data.hours_spent,
            description=data.description,
            entry_type=data.entry_type,
            is_billable=data.is_billable,
            status="DRAFT",
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)

        self._recompute_task_actual_hours(task.id)

        AuditService.log(
            self.db, "time_entry", entry.id, "CREATE",
            performed_by=self.current_user_id,
            new_value={
                "employee_id": str(employee_id),
                "task_id": str(data.task_id),
                "project_id": str(project_id),
                "date": str(data.date),
                "hours_spent": float(data.hours_spent),
                "entry_type": data.entry_type,
                "duplicate_warning": duplicate_exists > 0,
            },
        )

        return self._build_response(self._fetch_entry(entry.id))

    # ── Update ─────────────────────────────────────────────────────────────────

    def update(self, id: UUID, data: TimeEntryUpdate) -> TimeEntryResponse:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")

        if entry.status != "DRAFT":
            raise ValueError(
                f"Only DRAFT entries can be updated. Current status: {entry.status}"
            )

        # Ownership check — only the owner can update their own entry
        if entry.employee_id != self.current_user_id:
            raise ValueError("You can only update your own time entries")

        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return self._build_response(entry)

        old_values = {k: getattr(entry, k, None) for k in update_data}

        for key, value in update_data.items():
            setattr(entry, key, value)

        self.db.commit()
        self.db.refresh(entry)

        self._recompute_task_actual_hours(entry.task_id)

        AuditService.log(
            self.db, "time_entry", id, "UPDATE",
            performed_by=self.current_user_id,
            old_value=old_values,
            new_value=update_data,
        )

        return self._build_response(self._fetch_entry(id))

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete(self, id: UUID) -> None:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")

        # Ownership check
        if entry.employee_id != self.current_user_id:
            raise ValueError("You can only delete your own time entries")

        if entry.status not in ("DRAFT", "REJECTED"):
            raise ValueError(
                f"Only DRAFT or REJECTED entries can be deleted. Current status: {entry.status}"
            )

        task_id = entry.task_id

        AuditService.log(
            self.db, "time_entry", id, "DELETE",
            performed_by=self.current_user_id,
            old_value={
                "employee_id": str(entry.employee_id),
                "task_id": str(task_id),
                "date": str(entry.date),
                "hours_spent": float(entry.hours_spent),
                "status": entry.status,
            },
        )

        self.db.delete(entry)
        self.db.commit()

        self._recompute_task_actual_hours(task_id)

    # ── Submit ─────────────────────────────────────────────────────────────────

    def submit(self, id: UUID) -> TimeEntryResponse:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")

        # Ownership check
        if entry.employee_id != self.current_user_id:
            raise ValueError("You can only submit your own time entries")

        if entry.status != "DRAFT":
            raise ValueError(
                f"Only DRAFT entries can be submitted. Current status: {entry.status}"
            )

        entry.status = "SUBMITTED"
        entry.submitted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(entry)

        AuditService.log(
            self.db, "time_entry", id, "SUBMIT",
            performed_by=self.current_user_id,
            new_value={"status": "SUBMITTED", "submitted_at": str(entry.submitted_at)},
        )

        return self._build_response(self._fetch_entry(id))

    # ── Approve ────────────────────────────────────────────────────────────────

    def approve(self, id: UUID, approved_by_id: UUID) -> TimeEntryResponse:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")

        if entry.status != "SUBMITTED":
            raise ValueError(
                f"Only SUBMITTED entries can be approved. Current status: {entry.status}"
            )

        entry.status = "APPROVED"
        entry.approved_by = approved_by_id
        entry.approved_at = datetime.now(timezone.utc)
        entry.rejection_reason = None
        self.db.commit()
        self.db.refresh(entry)

        # Recompute to reflect approved status in task hours
        self._recompute_task_actual_hours(entry.task_id)

        AuditService.log(
            self.db, "time_entry", id, "APPROVE",
            performed_by=approved_by_id,
            new_value={
                "status": "APPROVED",
                "approved_by": str(approved_by_id),
                "approved_at": str(entry.approved_at),
            },
        )

        return self._build_response(self._fetch_entry(id))

    # ── Reject ─────────────────────────────────────────────────────────────────

    def reject(self, id: UUID, reason: str, rejected_by_id: UUID) -> TimeEntryResponse:
        entry = self._fetch_entry(id)
        if not entry:
            raise ValueError(f"Time entry with id {id} not found")

        if entry.status not in ("SUBMITTED", "APPROVED"):
            raise ValueError(
                f"Only SUBMITTED or APPROVED entries can be rejected. Current status: {entry.status}"
            )

        old_status = entry.status
        entry.status = "REJECTED"
        entry.rejection_reason = reason
        self.db.commit()
        self.db.refresh(entry)

        self._recompute_task_actual_hours(entry.task_id)

        AuditService.log(
            self.db, "time_entry", id, "REJECT",
            performed_by=rejected_by_id,
            old_value={"status": old_status},
            new_value={"status": "REJECTED", "rejection_reason": reason},
        )

        return self._build_response(self._fetch_entry(id))

    # ── Timesheet summary ──────────────────────────────────────────────────────

    def get_timesheet_summary(
        self, employee_id: UUID, date_from: date, date_to: date
    ) -> TimesheetSummary:
        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError(f"Employee with id {employee_id} not found")

        entries = self.db.scalars(
            select(TimeEntry)
            .options(
                joinedload(TimeEntry.task),
                joinedload(TimeEntry.project),
            )
            .where(
                TimeEntry.employee_id == employee_id,
                TimeEntry.date >= date_from,
                TimeEntry.date <= date_to,
            )
        ).unique().all()

        total_hours = sum(float(e.hours_spent) for e in entries)
        billable_hours = sum(float(e.hours_spent) for e in entries if e.is_billable)
        approved_hours = sum(float(e.hours_spent) for e in entries if e.status == "APPROVED")

        # Aggregate by project
        project_map: dict[uuid.UUID, dict] = {}
        for e in entries:
            pid = e.project_id
            project_name = (
                getattr(e.project, "name", None) if e.project else None
            ) or str(pid)
            if pid not in project_map:
                project_map[pid] = {
                    "project_id": str(pid),
                    "project_name": project_name,
                    "hours": 0.0,
                }
            project_map[pid]["hours"] = round(
                project_map[pid]["hours"] + float(e.hours_spent), 2
            )

        # Aggregate by task
        task_map: dict[uuid.UUID, dict] = {}
        for e in entries:
            tid = e.task_id
            task_code = getattr(e.task, "task_code", None) if e.task else None
            task_title = getattr(e.task, "title", None) if e.task else None
            if tid not in task_map:
                task_map[tid] = {
                    "task_id": str(tid),
                    "task_code": task_code,
                    "task_title": task_title,
                    "hours": 0.0,
                }
            task_map[tid]["hours"] = round(
                task_map[tid]["hours"] + float(e.hours_spent), 2
            )

        employee_name = f"{employee.first_name} {employee.last_name}"

        return TimesheetSummary(
            employee_id=employee_id,
            employee_name=employee_name,
            period_start=date_from,
            period_end=date_to,
            total_hours=round(total_hours, 2),
            billable_hours=round(billable_hours, 2),
            approved_hours=round(approved_hours, 2),
            by_project=list(project_map.values()),
            by_task=list(task_map.values()),
        )

    def get_my_timesheet(self, date_from: date, date_to: date) -> TimesheetSummary:
        if not self.current_user_id:
            raise ValueError("Current user is not set")
        return self.get_timesheet_summary(self.current_user_id, date_from, date_to)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _recompute_task_actual_hours(self, task_id: UUID) -> None:
        """Recompute task.actual_hours as sum of non-REJECTED time entries."""
        total = self.db.scalar(
            select(func.sum(TimeEntry.hours_spent)).where(
                TimeEntry.task_id == task_id,
                TimeEntry.status.not_in(["REJECTED"]),
            )
        ) or 0

        task = self.db.get(Task, task_id)
        if task:
            task.actual_hours = float(total)
            self.db.commit()

    def _fetch_entry(self, id: UUID) -> TimeEntry | None:
        return self.db.scalars(
            select(TimeEntry)
            .options(
                joinedload(TimeEntry.employee),
                joinedload(TimeEntry.task),
                joinedload(TimeEntry.project),
                joinedload(TimeEntry.approver),
            )
            .where(TimeEntry.id == id)
        ).unique().first()

    def _build_filters(
        self,
        employee_id: UUID | None,
        task_id: UUID | None,
        project_id: UUID | None,
        date_from: date | None,
        date_to: date | None,
        status: str | None,
    ) -> list:
        filters = []
        if employee_id:
            filters.append(TimeEntry.employee_id == employee_id)
        if task_id:
            filters.append(TimeEntry.task_id == task_id)
        if project_id:
            filters.append(TimeEntry.project_id == project_id)
        if date_from:
            filters.append(TimeEntry.date >= date_from)
        if date_to:
            filters.append(TimeEntry.date <= date_to)
        if status:
            filters.append(TimeEntry.status == status)
        return filters

    def _build_response(self, entry: TimeEntry) -> TimeEntryResponse:
        employee_name = employee_code = None
        if entry.employee:
            employee_name = f"{entry.employee.first_name} {entry.employee.last_name}"
            employee_code = entry.employee.employee_code

        task_code = task_title = None
        if entry.task:
            task_code = entry.task.task_code
            task_title = entry.task.title

        project_name = None
        if entry.project:
            project_name = getattr(entry.project, "name", None)

        return TimeEntryResponse(
            id=entry.id,
            employee_id=entry.employee_id,
            employee_name=employee_name,
            employee_code=employee_code,
            task_id=entry.task_id,
            task_code=task_code,
            task_title=task_title,
            project_id=entry.project_id,
            project_name=project_name,
            date=entry.date,
            hours_spent=float(entry.hours_spent),
            description=entry.description,
            entry_type=entry.entry_type,
            is_billable=entry.is_billable,
            status=entry.status,
            submitted_at=entry.submitted_at,
            approved_by=entry.approved_by,
            approved_at=entry.approved_at,
            rejection_reason=entry.rejection_reason,
            created_at=entry.created_at,
        )
