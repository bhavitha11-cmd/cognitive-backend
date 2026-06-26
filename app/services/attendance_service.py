from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.attendance_rule import AttendanceRule
from app.models.employee import Employee
from app.schemas.attendance import (
    AttendanceMarkRequest,
    AttendanceResponse,
    AttendanceRuleResponse,
    AttendanceRuleUpdate,
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
    """Return (is_late, late_by_minutes) relative to grace-period cutoff."""
    start_h, start_m = _parse_hhmm(office_start_time)
    # Build the grace-period cutoff in the same timezone as clock_in
    tz = clock_in.tzinfo or timezone.utc
    ref_date = clock_in.date()
    cutoff = datetime(
        ref_date.year, ref_date.month, ref_date.day,
        start_h, start_m, 0, tzinfo=tz
    ) + timedelta(minutes=late_mark_after_minutes)
    if clock_in > cutoff:
        diff_minutes = int((clock_in - cutoff).total_seconds() // 60)
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
            self.db.commit()
            self.db.refresh(record)
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
        except Exception:
            self.db.rollback()
            raise

        return _build_response(record)

    def get_by_employee(
        self,
        employee_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[AttendanceResponse]:
        self._get_employee_or_raise(employee_id)
        stmt = (
            select(Attendance)
            .where(Attendance.employee_id == employee_id)
            .order_by(Attendance.date.desc())
        )
        if from_date:
            stmt = stmt.where(Attendance.date >= from_date)
        if to_date:
            stmt = stmt.where(Attendance.date <= to_date)
        records = self.db.scalars(stmt).all()
        # Load employees for each record
        for r in records:
            self.db.refresh(r, attribute_names=["employee"])
        return [_build_response(r) for r in records]

    def get_by_date(
        self,
        record_date: date,
        department_id: uuid.UUID | None = None,
    ) -> list[AttendanceResponse]:
        stmt = (
            select(Attendance)
            .join(Attendance.employee)
            .where(Attendance.date == record_date)
            .order_by(Employee.last_name, Employee.first_name)
        )
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        records = self.db.scalars(stmt).all()
        for r in records:
            self.db.refresh(r, attribute_names=["employee"])
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

    def clock_in(
        self, employee_id: uuid.UUID, notes: str | None = None
    ) -> AttendanceResponse:
        self._get_employee_or_raise(employee_id)
        rule_obj = self.db.scalars(select(AttendanceRule)).first()
        if not rule_obj:
            rule_obj = AttendanceRule()
            self.db.add(rule_obj)
            self.db.flush()

        today = _now_utc().date()
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
            self.db.commit()
            self.db.refresh(record)
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

        today = _now_utc().date()
        record = self.db.scalars(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.date == today,
            )
        ).first()

        if not record:
            # Auto-create a record with only clock_out (edge case: forgot to clock in)
            record = Attendance(
                employee_id=employee_id,
                date=today,
                status="PRESENT",
                marked_by=self.current_user_id,
            )
            self.db.add(record)

        now = _now_utc()
        record.clock_out = now
        record.marked_by = self.current_user_id

        self._apply_hours(record, rule_obj)

        try:
            self.db.flush()
            self.db.commit()
            self.db.refresh(record)
            self.db.refresh(record, attribute_names=["employee"])
            AuditService.log(
                self.db,
                "attendance",
                record.id,
                "CLOCK_OUT",
                performed_by=self.current_user_id,
                new_value={
                    "employee_id": str(employee_id),
                    "date": str(today),
                    "clock_out": now.isoformat(),
                    "total_hours": float(record.total_hours or 0),
                    "overtime_hours": float(record.overtime_hours or 0),
                },
            )
        except Exception:
            self.db.rollback()
            raise

        return _build_response(record)
