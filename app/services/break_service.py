from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.org_time import business_date
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.employee_break import EmployeeBreak
from app.models.task_work_session import TaskWorkSession
from app.schemas.employee_break import BreakRead
from app.services.audit_service import AuditService


class BreakService:
    def __init__(self, db: Session, current_user_id: UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Start a break ────────────────────────────────────────────────────────
    # Rule 8: Starting a break pauses the current running task session

    def start_break(self, remarks: str | None = None) -> BreakRead:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        employee_id = self.current_user_id

        employee = self.db.get(Employee, employee_id)
        if not employee:
            raise ValueError("Employee not found")

        # Check employee is clocked in (IST business day)
        today = business_date()
        attendance = self.db.scalar(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == today,
                Attendance.clock_in.isnot(None),
                Attendance.clock_out.is_(None),
            )
        )
        if not attendance:
            raise ValueError(
                "You must be clocked in before taking a break"
            )

        # Check no active break already (any date, with row lock to prevent race)
        active_break = self.db.scalar(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == employee_id,
                EmployeeBreak.break_end.is_(None),
            )
            .with_for_update()  # Lock the row to prevent concurrent duplicate breaks
        )
        if active_break:
            raise ValueError("You already have an active break. End it first.")

        # Rule 8: Auto-pause current running task session
        running_session = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.status == "RUNNING",
            )
        )
        if running_session:
            now = datetime.now(timezone.utc)
            running_session.end_time = now
            running_session.status = "PAUSED"
            diff = (now - running_session.start_time).total_seconds() / 60.0
            running_session.duration_minutes += int(diff)
            running_session.pause_reason = "Auto-paused: break started"
            self.db.flush()

            AuditService.log(
                self.db,
                "task_work_session",
                running_session.id,
                "AUTO_PAUSE_BREAK",
                performed_by=self.current_user_id,
                new_value={"reason": "break_started"},
            )

        # Create break
        now = datetime.now(timezone.utc)
        break_record = EmployeeBreak(
            employee_id=employee_id,
            break_start=now,
            date=today,
            remarks=remarks,
        )
        self.db.add(break_record)

        try:
            # A partial unique index (WHERE break_end IS NULL) guards against
            # concurrent duplicate open breaks; surface it as a clean 4xx error.
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                raise ValueError("You already have an active break")

            AuditService.log(
                self.db,
                "employee_break",
                break_record.id,
                "BREAK_START",
                performed_by=self.current_user_id,
                new_value={
                    "date": str(today),
                    "break_start": now.isoformat(),
                },
            )
            self.db.commit()
        except ValueError:
            raise
        except Exception:
            self.db.rollback()
            raise

        return self._build_read(break_record)

    # ── End a break ──────────────────────────────────────────────────────────
    # Rule 8: Ending a break resumes the paused task session

    def end_break(self, remarks: str | None = None) -> BreakRead:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        employee_id = self.current_user_id

        # Close the most recent open break regardless of date so a stale
        # prior-day open break can still be ended.
        active_break = self.db.scalar(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == employee_id,
                EmployeeBreak.break_end.is_(None),
            )
            .order_by(EmployeeBreak.break_start.desc())
        )
        if not active_break:
            raise ValueError("No active break found")

        # End the break
        now = datetime.now(timezone.utc)
        start = active_break.break_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        diff = max(0, int((now - start).total_seconds() / 60.0))
        active_break.break_end = now
        active_break.duration_minutes = diff
        if remarks:
            active_break.remarks = remarks

        # Resume the most recently paused session (if any)
        paused_session = self.db.scalar(
            select(TaskWorkSession).where(
                TaskWorkSession.employee_id == employee_id,
                TaskWorkSession.status == "PAUSED",
                TaskWorkSession.pause_reason == "Auto-paused: break started",
            )
            .order_by(TaskWorkSession.end_time.desc())
        )
        if paused_session:
            paused_session.start_time = now
            paused_session.end_time = None
            paused_session.status = "RUNNING"
            paused_session.pause_reason = None
            self.db.flush()

            AuditService.log(
                self.db,
                "task_work_session",
                paused_session.id,
                "AUTO_RESUME_BREAK",
                performed_by=self.current_user_id,
                new_value={"reason": "break_ended"},
            )

        try:
            self.db.flush()
            AuditService.log(
                self.db,
                "employee_break",
                active_break.id,
                "BREAK_END",
                performed_by=self.current_user_id,
                new_value={
                    "duration_minutes": diff,
                    "break_end": now.isoformat(),
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return self._build_read(active_break)

    # ── Get active break ─────────────────────────────────────────────────────

    def get_active_break(self) -> BreakRead | None:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        active_break = self.db.scalar(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == self.current_user_id,
                EmployeeBreak.break_end.is_(None),
            )
            .order_by(EmployeeBreak.break_start.desc())
        )
        if not active_break:
            return None
        return self._build_read(active_break)

    # ── Get breaks for current user ──────────────────────────────────────────

    def get_my_breaks(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[BreakRead], int]:
        if not self.current_user_id:
            raise ValueError("Current user is not set")

        base_q = select(EmployeeBreak).where(
            EmployeeBreak.employee_id == self.current_user_id
        )
        count_q = select(func.count()).select_from(EmployeeBreak).where(
            EmployeeBreak.employee_id == self.current_user_id
        )

        if date_from:
            base_q = base_q.where(EmployeeBreak.date >= date_from)
            count_q = count_q.where(EmployeeBreak.date >= date_from)
        if date_to:
            base_q = base_q.where(EmployeeBreak.date <= date_to)
            count_q = count_q.where(EmployeeBreak.date <= date_to)

        total = self.db.scalar(count_q) or 0
        breaks = self.db.scalars(
            base_q.order_by(EmployeeBreak.break_start.desc())
            .offset(skip)
            .limit(limit)
        ).all()

        return [self._build_read(b) for b in breaks], total

    # ── Internal ─────────────────────────────────────────────────────────────

    def _build_read(self, break_record: EmployeeBreak) -> BreakRead:
        return BreakRead(
            id=break_record.id,
            employee_id=break_record.employee_id,
            break_start=break_record.break_start,
            break_end=break_record.break_end,
            duration_minutes=break_record.duration_minutes,
            date=break_record.date,
            remarks=break_record.remarks,
            created_at=break_record.created_at,
        )
