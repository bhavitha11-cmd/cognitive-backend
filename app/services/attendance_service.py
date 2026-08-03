from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.core.org_time import org_now, to_org, business_date
from app.models.attendance import Attendance
from app.models.attendance_rule import AttendanceRule
from app.models.employee import Employee
from app.models.missed_clockout_request import MissedClockoutRequest
from app.models.missed_clockin_request import MissedClockinRequest
from app.schemas.attendance import (
    AttendanceMarkRequest,
    AttendanceResponse,
    AttendanceRuleResponse,
    AttendanceRuleUpdate,
    MissedClockoutRequestCreate,
    MissedClockoutRequestResponse,
    MissedClockinRequestCreate,
    MissedClockinRequestResponse,
)
from app.services.audit_service import AuditService



def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_hhmm(time_str: str) -> tuple[int, int]:
    """Return (hour, minute) from an 'HH:MM' string."""
    h, m = time_str.split(":")
    return int(h), int(m)


def _compute_late(
    clock_in: datetime,
    office_start_time: str,
    late_mark_after_minutes: int,
) -> tuple[bool, int]:
    """Return (is_late, late_by_minutes) relative to grace-period cutoff.

    The office_start cutoff is built in the ORG timezone (Asia/Kolkata): the
    clock_in is converted to org-local time and the cutoff is derived from
    office_start_time on that org-local date.  This avoids systematically-wrong
    late marks caused by comparing an IST office start against a UTC clock_in.
    """
    start_h, start_m = _parse_hhmm(office_start_time)
    # Convert clock_in into the org timezone and build the cutoff there.
    if clock_in.tzinfo is None:
        clock_in = clock_in.replace(tzinfo=timezone.utc)
    org_ci = to_org(clock_in)
    cutoff = org_ci.replace(
        hour=start_h, minute=start_m, second=0, microsecond=0
    ) + timedelta(minutes=late_mark_after_minutes)
    if org_ci > cutoff:
        diff_minutes = int((org_ci - cutoff).total_seconds() // 60)
        return True, diff_minutes
    return False, 0


def _build_response(record: Attendance) -> AttendanceResponse:
    """Convert an ORM Attendance object to AttendanceResponse, enriching with
    employee name/code if the relationship is loaded."""
    employee_name: str | None = None
    employee_code: str | None = None
    if record.employee:
        emp = record.employee
        parts = [emp.first_name or "", emp.last_name or ""]
        employee_name = " ".join(p for p in parts if p).strip() or None
        employee_code = emp.employee_code

    return AttendanceResponse(
        id=record.id,
        employee_id=record.employee_id,
        employee_name=employee_name,
        employee_code=employee_code,
        date=record.date,
        clock_in=record.clock_in,
        clock_out=record.clock_out,
        total_hours=float(record.total_hours or 0),
        status=record.status,
        is_late=bool(record.is_late),
        late_by_minutes=int(record.late_by_minutes or 0),
        overtime_hours=float(record.overtime_hours or 0),
        notes=record.notes,
        created_at=record.created_at,
    )


class AttendanceService:
    def __init__(self, db: Session, current_user_id: uuid.UUID | None = None):
        self.db = db
        self.current_user_id = current_user_id

    # ── Rule management ───────────────────────────────────────────────────────

    def get_rule(self) -> AttendanceRuleResponse:
        """Return the single org-level attendance rule, creating defaults if absent."""
        rule = self.db.scalars(select(AttendanceRule)).first()
        if not rule:
            rule = AttendanceRule()
            self.db.add(rule)
            self.db.commit()
            self.db.refresh(rule)
        return AttendanceRuleResponse.model_validate(rule)

    def update_rule(self, data: AttendanceRuleUpdate) -> AttendanceRuleResponse:
        rule = self.db.scalars(select(AttendanceRule)).first()
        if not rule:
            rule = AttendanceRule()
            self.db.add(rule)
            self.db.flush()

        update_data = data.model_dump(exclude_unset=True)
        old_values = {k: getattr(rule, k, None) for k in update_data}

        for field, value in update_data.items():
            setattr(rule, field, value)

        try:
            self.db.commit()
            self.db.refresh(rule)
            
            # Clear productivity policy resolver cache
            try:
                from app.services.productivity.policy_resolver import PolicyResolver
                PolicyResolver.clear_cache()
            except ImportError:
                pass

            AuditService.log(
                self.db,
                "attendance_rule",
                rule.id,
                "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values,
                new_value=update_data,
            )
        except Exception:
            self.db.rollback()
            raise

        return AttendanceRuleResponse.model_validate(rule)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_employee_or_raise(self, employee_id: uuid.UUID) -> Employee:
        emp = self.db.get(Employee, employee_id)
        if not emp:
            raise ValueError(f"Employee with id {employee_id} not found")
        return emp

    def _get_or_create_record(
        self, employee_id: uuid.UUID, record_date: date
    ) -> tuple[Attendance, bool]:
        """Return (record, is_new).  Does NOT flush/commit."""
        existing = self.db.scalars(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == record_date,
            )
        ).first()
        if existing:
            return existing, False
        new_record = Attendance(
            employee_id=employee_id,
            date=record_date,
            marked_by=self.current_user_id,
        )
        self.db.add(new_record)
        return new_record, True

    def _apply_hours(
        self, record: Attendance, rule: AttendanceRule
    ) -> None:
        """Recompute total_hours and overtime_hours from clock_in / clock_out."""
        if record.clock_in and record.clock_out:
            delta = record.clock_out - record.clock_in
            total = delta.total_seconds() / 3600.0
            record.total_hours = round(max(0.0, total), 2)
            record.overtime_hours = round(max(0.0, total - float(rule.overtime_threshold_hours)), 2)
        else:
            record.total_hours = 0.0
            record.overtime_hours = 0.0

    # Statuses set by an admin that must never be overridden by hours-based logic.
    _PROTECTED_STATUSES = {"ON_LEAVE", "HOLIDAY", "WFH"}

    def _apply_half_day_status(self, record: Attendance, rule: AttendanceRule) -> None:
        """After a clock_out exists, downgrade to HALF_DAY when total hours fall
        below the rule's half-day threshold, else mark PRESENT.  Never overrides
        an admin-set ON_LEAVE / HOLIDAY / WFH status."""
        if record.clock_out is None:
            return
        if record.status in self._PROTECTED_STATUSES:
            return
        total = float(record.total_hours or 0)
        if total < float(rule.half_day_hours):
            record.status = "HALF_DAY"
        else:
            record.status = "PRESENT"

    def _apply_late(self, record: Attendance, rule: AttendanceRule) -> None:
        """Recompute is_late / late_by_minutes from clock_in."""
        if record.clock_in:
            is_late, late_mins = _compute_late(
                record.clock_in,
                rule.office_start_time,
                int(rule.late_mark_after_minutes),
            )
            record.is_late = is_late
            record.late_by_minutes = late_mins
        else:
            record.is_late = False
            record.late_by_minutes = 0

    # ── Core operations ───────────────────────────────────────────────────────

    def mark_attendance(self, data: AttendanceMarkRequest) -> AttendanceResponse:
        """Upsert an attendance record.  Computes hours, late-marks, and overtime."""
        self._get_employee_or_raise(data.employee_id)
        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        record, is_new = self._get_or_create_record(data.employee_id, data.date)

        old_values: dict = {}
        if not is_new:
            old_values = {
                "status": record.status,
                "clock_in": record.clock_in.isoformat() if record.clock_in else None,
                "clock_out": record.clock_out.isoformat() if record.clock_out else None,
                "notes": record.notes,
            }

        # Validate clock_out is strictly after clock_in.  Determine the
        # effective clock_in/clock_out that will be stored, then reject an
        # invalid ordering rather than silently clamping hours to zero.
        effective_ci = data.clock_in if data.clock_in is not None else record.clock_in
        effective_co = data.clock_out if data.clock_out is not None else record.clock_out
        if effective_co is not None and effective_ci is not None:
            ci_cmp = effective_ci
            co_cmp = effective_co
            if ci_cmp.tzinfo is None:
                ci_cmp = ci_cmp.replace(tzinfo=timezone.utc)
            if co_cmp.tzinfo is None:
                co_cmp = co_cmp.replace(tzinfo=timezone.utc)
            if co_cmp <= ci_cmp:
                raise ValueError("clock_out must be after clock_in")

        record.status = data.status
        if data.clock_in is not None:
            record.clock_in = data.clock_in
        if data.clock_out is not None:
            record.clock_out = data.clock_out
        if data.notes is not None:
            record.notes = data.notes
        record.marked_by = self.current_user_id

        self._apply_late(record, rule_obj)
        self._apply_hours(record, rule_obj)

        try:
            self.db.flush()
            # Eagerly load employee for response enrichment
            self.db.refresh(record, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "attendance",
                record.id,
                "CREATE" if is_new else "UPDATE",
                performed_by=self.current_user_id,
                old_value=old_values if not is_new else None,
                new_value={
                    "employee_id": str(data.employee_id),
                    "date": str(data.date),
                    "status": record.status,
                    "clock_in": record.clock_in.isoformat() if record.clock_in else None,
                    "clock_out": record.clock_out.isoformat() if record.clock_out else None,
                },
            )
            self.db.commit()
            self.db.refresh(record)
            self.db.refresh(record, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return _build_response(record)

    def get_by_employee(
        self,
        employee_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> list[AttendanceResponse]:
        self._get_employee_or_raise(employee_id)
        skip = max(0, skip)
        limit = max(1, min(limit, 200))
        stmt = (
            select(Attendance)
            .options(selectinload(Attendance.employee))
            .where(Attendance.employee_id == employee_id)
            .order_by(Attendance.date.desc())
        )
        if from_date:
            stmt = stmt.where(Attendance.date >= from_date)
        if to_date:
            stmt = stmt.where(Attendance.date <= to_date)
        stmt = stmt.offset(skip).limit(limit)
        records = self.db.scalars(stmt).all()
        return [_build_response(r) for r in records]

    def get_by_date(
        self,
        record_date: date,
        department_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> list[AttendanceResponse]:
        skip = max(0, skip)
        limit = max(1, min(limit, 200))
        stmt = (
            select(Attendance)
            .join(Attendance.employee)
            .options(selectinload(Attendance.employee))
            .where(Attendance.date == record_date)
            .order_by(Employee.last_name, Employee.first_name)
        )
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        stmt = stmt.offset(skip).limit(limit)
        records = self.db.scalars(stmt).all()
        return [_build_response(r) for r in records]

    def get_by_date_range(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        department_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 500,
    ) -> list[AttendanceResponse]:
        skip = max(0, skip)
        limit = max(1, min(limit, 500))
        stmt = (
            select(Attendance)
            .join(Attendance.employee)
            .options(selectinload(Attendance.employee))
            .order_by(Attendance.date.desc(), Employee.last_name, Employee.first_name)
        )
        if from_date:
            stmt = stmt.where(Attendance.date >= from_date)
        if to_date:
            stmt = stmt.where(Attendance.date <= to_date)
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        stmt = stmt.offset(skip).limit(limit)
        records = self.db.scalars(stmt).all()
        return [_build_response(r) for r in records]

    def get_summary(
        self,
        employee_id: uuid.UUID,
        year: int,
        month: int,
    ) -> dict:
        self._get_employee_or_raise(employee_id)

        from calendar import monthrange
        _, last_day = monthrange(year, month)
        from_date = date(year, month, 1)
        to_date = date(year, month, last_day)

        stmt = select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.date >= from_date,
            Attendance.date <= to_date,
        )
        records = self.db.scalars(stmt).all()

        present_count = sum(1 for r in records if r.status == "PRESENT")
        absent_count = sum(1 for r in records if r.status == "ABSENT")
        half_day_count = sum(1 for r in records if r.status == "HALF_DAY")
        wfh_count = sum(1 for r in records if r.status == "WFH")
        on_leave_count = sum(1 for r in records if r.status == "ON_LEAVE")
        holiday_count = sum(1 for r in records if r.status == "HOLIDAY")
        late_count = sum(1 for r in records if r.is_late)
        total_hours = sum(float(r.total_hours or 0) for r in records)
        overtime_hours = sum(float(r.overtime_hours or 0) for r in records)

        return {
            "employee_id": str(employee_id),
            "year": year,
            "month": month,
            "present_count": present_count,
            "absent_count": absent_count,
            "half_day_count": half_day_count,
            "wfh_count": wfh_count,
            "on_leave_count": on_leave_count,
            "holiday_count": holiday_count,
            "late_count": late_count,
            "total_hours": round(total_hours, 2),
            "overtime_hours": round(overtime_hours, 2),
            "total_records": len(records),
        }

    # ── Self-service clock-in / clock-out ─────────────────────────────────────

    def auto_close_missed_clockouts(
        self,
        max_hours: float = 10.0,
        target_date: date | None = None,
    ) -> list[AttendanceResponse]:
        """
        Find all attendance records with a clock_in but no clock_out where
        clock_in + max_hours has already passed, and auto-close them.

        - target_date: restrict to a specific date; omit to process all open records
          through today.
        - max_hours: how many hours after clock_in to set as the auto clock-out time
          (default 10 h).

        Returns the list of records that were closed.
        """
        now = _now_utc()
        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        stmt = select(Attendance).where(
            Attendance.clock_in.isnot(None),
            Attendance.clock_out.is_(None),
        )
        if target_date:
            stmt = stmt.where(Attendance.date == target_date)
        else:
            stmt = stmt.where(Attendance.date <= business_date())

        records = self.db.scalars(stmt).all()
        closed: list[Attendance] = []

        try:
            for rec in records:
                ci = rec.clock_in
                if ci is None:
                    continue
                if ci.tzinfo is None:
                    ci = ci.replace(tzinfo=timezone.utc)
                expected_out = ci + timedelta(hours=max_hours)
                if now < expected_out:
                    continue  # not yet overdue

                rec.clock_out = expected_out
                rec.notes = (
                    (rec.notes + "\n" if rec.notes else "")
                    + f"Auto clock-out: missed checkout (system-closed after {max_hours:.0f}h at {expected_out.strftime('%H:%M')} UTC; overtime not credited)"
                )
                self._apply_hours(rec, rule_obj)
                # System-closed records must NOT fabricate overtime.
                rec.overtime_hours = 0.0
                self._apply_half_day_status(rec, rule_obj)
                closed.append(rec)

                AuditService.log(
                    self.db,
                    "attendance",
                    rec.id,
                    "AUTO_CLOCK_OUT",
                    performed_by=self.current_user_id,
                    old_value={"clock_out": None},
                    new_value={
                        "employee_id": str(rec.employee_id),
                        "date": str(rec.date),
                        "clock_out": expected_out.isoformat(),
                        "reason": "missed_checkout",
                        "max_hours": max_hours,
                        "system_closed": True,
                        "overtime_hours": 0.0,
                    },
                )

            if closed:
                self.db.commit()
                for rec in closed:
                    self.db.refresh(rec)
                    self.db.refresh(rec, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return [_build_response(r) for r in closed]

    def clock_in(
        self, employee_id: uuid.UUID, notes: str | None = None
    ) -> AttendanceResponse:
        self._get_employee_or_raise(employee_id)
        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        # Key the attendance row on the IST business date; store the timestamp
        # itself as UTC (aware) below.
        today = business_date()

        # Guard: prevent overwriting an existing clock-in
        existing = self.db.scalar(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == today,
                Attendance.clock_in.isnot(None),
            )
        )
        if existing:
            raise ValueError("Already clocked in for today")

        record, is_new = self._get_or_create_record(employee_id, today)

        now = _now_utc()
        record.clock_in = now
        record.status = "PRESENT"
        record.marked_by = self.current_user_id
        if notes is not None:
            record.notes = notes

        self._apply_late(record, rule_obj)
        self._apply_hours(record, rule_obj)

        try:
            self.db.flush()
            self.db.refresh(record, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "attendance",
                record.id,
                "CLOCK_IN",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(employee_id),
                    "date": str(today),
                    "clock_in": now.isoformat(),
                    "is_late": record.is_late,
                    "late_by_minutes": record.late_by_minutes,
                },
            )
            self.db.commit()
            self.db.refresh(record)
            self.db.refresh(record, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return _build_response(record)

    def clock_out(self, employee_id: uuid.UUID) -> AttendanceResponse:
        self._get_employee_or_raise(employee_id)
        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        # H3 cross-midnight clock-out: pick the most recent open attendance row
        # (clock_in set, clock_out NULL) whose clock_in is within the last ~36h,
        # rather than strictly today's row.  This lets a shift that started
        # yesterday (IST) be closed after midnight.
        now = _now_utc()
        window_start = now - timedelta(hours=36)
        record = self.db.scalars(
            select(Attendance)
            .where(
                Attendance.employee_id == employee_id,
                Attendance.clock_in.isnot(None),
                Attendance.clock_out.is_(None),
                Attendance.clock_in >= window_start,
            )
            .order_by(Attendance.clock_in.desc())
        ).first()

        if not record or record.clock_in is None:
            raise ValueError(
                "No clock-in record found for today. Please contact HR to record your attendance manually."
            )

        record.clock_out = now
        record.marked_by = self.current_user_id

        self._apply_hours(record, rule_obj)
        self._apply_half_day_status(record, rule_obj)

        # Rule 8: force-close any open break for this employee (compute duration).
        self._close_open_breaks(employee_id)

        try:
            self.db.flush()
            self.db.refresh(record, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "attendance",
                record.id,
                "CLOCK_OUT",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(employee_id),
                    "date": str(record.date),
                    "clock_out": now.isoformat(),
                    "total_hours": float(record.total_hours or 0),
                    "overtime_hours": float(record.overtime_hours or 0),
                    "status": record.status,
                },
            )
            self.db.commit()
            self.db.refresh(record)
            self.db.refresh(record, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return _build_response(record)

    def _close_open_breaks(self, employee_id: uuid.UUID) -> None:
        """Force-close any open (break_end IS NULL) breaks for the employee,
        computing their duration.  Handles stale prior-day open breaks too.
        Does NOT commit — the caller commits within its own transaction."""
        from app.models.employee_break import EmployeeBreak

        now = _now_utc()
        open_breaks = self.db.scalars(
            select(EmployeeBreak).where(
                EmployeeBreak.employee_id == employee_id,
                EmployeeBreak.break_end.is_(None),
            )
        ).all()
        for brk in open_breaks:
            start = brk.break_start
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            brk.break_end = now
            brk.duration_minutes = max(0, int((now - start).total_seconds() / 60.0))
            AuditService.log(
                self.db,
                "employee_break",
                brk.id,
                "BREAK_FORCE_CLOSE",
                performed_by=self.current_user_id,
                new_value={
                    "reason": "clock_out",
                    "break_end": now.isoformat(),
                    "duration_minutes": brk.duration_minutes,
                },
            )
        if open_breaks:
            self.db.flush()

    # ── Missed clock-out request flow ─────────────────────────────────────────

    def _build_mcr_response(self, req: MissedClockoutRequest) -> MissedClockoutRequestResponse:
        emp = req.employee
        employee_name: str | None = None
        employee_code: str | None = None
        if emp:
            parts = [emp.first_name or "", emp.last_name or ""]
            employee_name = " ".join(p for p in parts if p).strip() or None
            employee_code = emp.employee_code
        return MissedClockoutRequestResponse(
            id=req.id,
            employee_id=req.employee_id,
            employee_name=employee_name,
            employee_code=employee_code,
            attendance_date=req.attendance_date,
            requested_clock_out=req.requested_clock_out,
            reason=req.reason,
            status=req.status,
            reviewed_by=req.reviewed_by,
            reviewed_at=req.reviewed_at,
            review_notes=req.review_notes,
            created_at=req.created_at,
        )

    def submit_missed_clockout_request(
        self, employee_id: uuid.UUID, data: MissedClockoutRequestCreate
    ) -> MissedClockoutRequestResponse:
        self._get_employee_or_raise(employee_id)

        record = self.db.scalars(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == data.attendance_date,
            )
        ).first()
        if not record or record.clock_in is None:
            raise ValueError(
                f"No clock-in found for {data.attendance_date}. "
                "HR can manually mark your attendance instead."
            )
        if record.clock_out is not None:
            raise ValueError(f"A clock-out already exists for {data.attendance_date}.")

        ci = record.clock_in
        if ci.tzinfo is None:
            ci = ci.replace(tzinfo=timezone.utc)
        rco = data.requested_clock_out
        if rco.tzinfo is None:
            rco = rco.replace(tzinfo=timezone.utc)
        if rco <= ci:
            raise ValueError("Requested clock-out time must be after your clock-in time.")
        if rco > _now_utc():
            raise ValueError("Requested clock-out time cannot be in the future.")

        existing_pending = self.db.scalars(
            select(MissedClockoutRequest).where(
                MissedClockoutRequest.employee_id == employee_id,
                MissedClockoutRequest.attendance_date == data.attendance_date,
                MissedClockoutRequest.status == "PENDING",
            )
        ).first()
        if existing_pending:
            raise ValueError(
                "You already have a pending missed clock-out request for this date."
            )

        req = MissedClockoutRequest(
            employee_id=employee_id,
            attendance_date=data.attendance_date,
            requested_clock_out=rco,
            reason=data.reason,
            status="PENDING",
        )
        self.db.add(req)
        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockout_request",
                req.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(employee_id),
                    "attendance_date": str(data.attendance_date),
                    "requested_clock_out": rco.isoformat(),
                    "reason": data.reason,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_mcr_response(req)

    def list_missed_clockout_requests(
        self,
        status: str | None = None,
        employee_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> list[MissedClockoutRequestResponse]:
        skip = max(0, skip)
        limit = max(1, min(limit, 200))
        stmt = (
            select(MissedClockoutRequest)
            .options(selectinload(MissedClockoutRequest.employee))
            .order_by(MissedClockoutRequest.created_at.desc())
        )
        if status:
            stmt = stmt.where(MissedClockoutRequest.status == status)
        if employee_id:
            stmt = stmt.where(MissedClockoutRequest.employee_id == employee_id)
        stmt = stmt.offset(skip).limit(limit)
        requests = self.db.scalars(stmt).all()
        return [self._build_mcr_response(r) for r in requests]

    def approve_missed_clockout_request(
        self,
        request_id: uuid.UUID,
        review_notes: str | None = None,
    ) -> MissedClockoutRequestResponse:
        req = self.db.get(MissedClockoutRequest, request_id)
        if not req:
            raise ValueError("Request not found.")
        if req.status != "PENDING":
            raise ValueError(f"Request is already {req.status}.")

        # H9: an employee cannot approve their own missed clock-out request.
        if self.current_user_id is not None and req.employee_id == self.current_user_id:
            raise ValueError("You cannot approve your own missed clock-out request.")

        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        attendance = self.db.scalars(
            select(Attendance).where(
                Attendance.employee_id == req.employee_id,
                Attendance.date == req.attendance_date,
            )
        ).first()
        if attendance:
            attendance.clock_out = req.requested_clock_out
            attendance.notes = (
                (attendance.notes + "\n" if attendance.notes else "")
                + f"Clock-out approved by admin (missed clockout request #{str(req.id)[:8]})"
            )
            self._apply_hours(attendance, rule_obj)
            self._apply_half_day_status(attendance, rule_obj)

        now = _now_utc()
        req.status = "APPROVED"
        req.reviewed_by = self.current_user_id
        req.reviewed_at = now
        req.review_notes = review_notes

        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockout_request",
                req.id,
                "APPROVE",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(req.employee_id),
                    "attendance_date": str(req.attendance_date),
                    "approved_clock_out": req.requested_clock_out.isoformat(),
                    "review_notes": review_notes,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_mcr_response(req)

    def reject_missed_clockout_request(
        self,
        request_id: uuid.UUID,
        review_notes: str | None = None,
    ) -> MissedClockoutRequestResponse:
        req = self.db.get(MissedClockoutRequest, request_id)
        if not req:
            raise ValueError("Request not found.")
        if req.status != "PENDING":
            raise ValueError(f"Request is already {req.status}.")

        now = _now_utc()
        req.status = "REJECTED"
        req.reviewed_by = self.current_user_id
        req.reviewed_at = now
        req.review_notes = review_notes

        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockout_request",
                req.id,
                "REJECT",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(req.employee_id),
                    "attendance_date": str(req.attendance_date),
                    "review_notes": review_notes,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_mcr_response(req)

    # ── Missed clock-in request flow ─────────────────────────────────────────

    def _build_micr_response(self, req: MissedClockinRequest) -> MissedClockinRequestResponse:
        emp = req.employee
        employee_name: str | None = None
        employee_code: str | None = None
        if emp:
            parts = [emp.first_name or "", emp.last_name or ""]
            employee_name = " ".join(p for p in parts if p).strip() or None
            employee_code = emp.employee_code
        return MissedClockinRequestResponse(
            id=req.id,
            employee_id=req.employee_id,
            employee_name=employee_name,
            employee_code=employee_code,
            attendance_date=req.attendance_date,
            requested_clock_in=req.requested_clock_in,
            reason=req.reason,
            status=req.status,
            reviewed_by=req.reviewed_by,
            reviewed_at=req.reviewed_at,
            review_notes=req.review_notes,
            created_at=req.created_at,
        )

    def submit_missed_clockin_request(
        self, employee_id: uuid.UUID, data: MissedClockinRequestCreate
    ) -> MissedClockinRequestResponse:
        self._get_employee_or_raise(employee_id)

        record = self.db.scalars(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == data.attendance_date,
            )
        ).first()

        if record and record.clock_in is not None:
            raise ValueError(f"A clock-in already exists for {data.attendance_date}.")

        rci = data.requested_clock_in
        if rci.tzinfo is None:
            rci = rci.replace(tzinfo=timezone.utc)
        if rci > _now_utc():
            raise ValueError("Requested clock-in time cannot be in the future.")

        if record and record.clock_out is not None:
            co = record.clock_out
            if co.tzinfo is None:
                co = co.replace(tzinfo=timezone.utc)
            if rci >= co:
                raise ValueError("Requested clock-in time must be before your clock-out time.")

        existing_pending = self.db.scalars(
            select(MissedClockinRequest).where(
                MissedClockinRequest.employee_id == employee_id,
                MissedClockinRequest.attendance_date == data.attendance_date,
                MissedClockinRequest.status == "PENDING",
            )
        ).first()
        if existing_pending:
            raise ValueError(
                "You already have a pending missed clock-in request for this date."
            )

        req = MissedClockinRequest(
            employee_id=employee_id,
            attendance_date=data.attendance_date,
            requested_clock_in=rci,
            reason=data.reason,
            status="PENDING",
        )
        self.db.add(req)
        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockin_request",
                req.id,
                "CREATE",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(employee_id),
                    "attendance_date": str(data.attendance_date),
                    "requested_clock_in": rci.isoformat(),
                    "reason": data.reason,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_micr_response(req)

    def list_missed_clockin_requests(
        self,
        status: str | None = None,
        employee_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> list[MissedClockinRequestResponse]:
        skip = max(0, skip)
        limit = max(1, min(limit, 200))
        stmt = (
            select(MissedClockinRequest)
            .options(selectinload(MissedClockinRequest.employee))
            .order_by(MissedClockinRequest.created_at.desc())
        )
        if status:
            stmt = stmt.where(MissedClockinRequest.status == status)
        if employee_id:
            stmt = stmt.where(MissedClockinRequest.employee_id == employee_id)
        stmt = stmt.offset(skip).limit(limit)
        requests = self.db.scalars(stmt).all()
        return [self._build_micr_response(r) for r in requests]

    def approve_missed_clockin_request(
        self,
        request_id: uuid.UUID,
        review_notes: str | None = None,
    ) -> MissedClockinRequestResponse:
        req = self.db.get(MissedClockinRequest, request_id)
        if not req:
            raise ValueError("Request not found.")
        if req.status != "PENDING":
            raise ValueError(f"Request is already {req.status}.")

        if self.current_user_id is not None and req.employee_id == self.current_user_id:
            raise ValueError("You cannot approve your own missed clock-in request.")

        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        attendance, is_new = self._get_or_create_record(req.employee_id, req.attendance_date)
        
        if not is_new and attendance.clock_in is not None:
            raise ValueError("An attendance record with a clock-in already exists for this date.")

        attendance.clock_in = req.requested_clock_in
        attendance.notes = (
            (attendance.notes + "\n" if attendance.notes else "")
            + f"Clock-in approved by admin (missed clockin request #{str(req.id)[:8]})"
        )
        
        if attendance.status in {"ABSENT", "ON_LEAVE", "HOLIDAY"} and not is_new:
            attendance.status = "PRESENT"
        elif is_new:
            attendance.status = "PRESENT"

        self._apply_late(attendance, rule_obj)
        self._apply_hours(attendance, rule_obj)
        self._apply_half_day_status(attendance, rule_obj)

        now = _now_utc()
        req.status = "APPROVED"
        req.reviewed_by = self.current_user_id
        req.reviewed_at = now
        req.review_notes = review_notes

        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockin_request",
                req.id,
                "APPROVE",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(req.employee_id),
                    "attendance_date": str(req.attendance_date),
                    "approved_clock_in": req.requested_clock_in.isoformat(),
                    "review_notes": review_notes,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_micr_response(req)

    def reject_missed_clockin_request(
        self,
        request_id: uuid.UUID,
        review_notes: str | None = None,
    ) -> MissedClockinRequestResponse:
        req = self.db.get(MissedClockinRequest, request_id)
        if not req:
            raise ValueError("Request not found.")
        if req.status != "PENDING":
            raise ValueError(f"Request is already {req.status}.")

        now = _now_utc()
        req.status = "REJECTED"
        req.reviewed_by = self.current_user_id
        req.reviewed_at = now
        req.review_notes = review_notes

        try:
            self.db.flush()
            self.db.refresh(req, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "missed_clockin_request",
                req.id,
                "REJECT",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(req.employee_id),
                    "attendance_date": str(req.attendance_date),
                    "review_notes": review_notes,
                },
            )
            self.db.commit()
            self.db.refresh(req)
            self.db.refresh(req, attribute_names=["employee"])
        except Exception:
            self.db.rollback()
            raise

        return self._build_micr_response(req)
