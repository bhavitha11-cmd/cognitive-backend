from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.attendance import Attendance
from app.models.attendance_rule import AttendanceRule
from app.models.employee import Employee
from app.models.missed_clockin_request import MissedClockinRequest
from app.schemas.attendance import MissedClockinRequestCreate
from app.services.attendance_service import AttendanceService
from tests.conftest import TEST_EMPLOYEE_ID, make_mock_employee


@pytest.fixture
def attendance_service(mock_db):
    return AttendanceService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)


def make_mock_attendance_record(
    id=uuid.uuid4(),
    employee_id=TEST_EMPLOYEE_ID,
    attendance_date=date(2026, 7, 9),
    clock_in=None,
    clock_out=None,
    status="ABSENT",
):
    att = MagicMock(spec=Attendance)
    att.id = id
    att.employee_id = employee_id
    att.date = attendance_date
    att.clock_in = clock_in
    att.clock_out = clock_out
    att.status = status
    att.total_hours = 0.0
    att.overtime_hours = 0.0
    att.is_late = False
    att.late_by_minutes = 0
    att.notes = None
    att.employee = make_mock_employee(id=employee_id)
    return att


class TestMissedClockinRequest:
    # ── Submit Request ──────────────────────────────────────────────────────────

    def test_submit_missed_clockin_blocked_without_workflow(self, attendance_service, mock_db):
        mock_emp = make_mock_employee()
        mock_db.get.return_value = mock_emp

        # Mock query return: no attendance record exists yet, no pending request exists,
        # and no active ATTENDANCE_CORRECTION approval workflow is configured — submission
        # must be blocked (mirrors LEAVE: no silent fallback to the old direct
        # admin approve/reject endpoints).
        mock_db.scalars.return_value.first.side_effect = [
            None,  # No existing attendance record
            None,  # No existing pending request
            None,  # No active ApprovalWorkflow for ATTENDANCE_CORRECTION
        ]

        req_time = datetime.now(timezone.utc) - timedelta(hours=1)
        data = MissedClockinRequestCreate(
            attendance_date=date(2026, 7, 9),
            requested_clock_in=req_time,
            reason="Forgot to mark login",
        )

        with pytest.raises(ValueError, match="No active approval workflow configured"):
            attendance_service.submit_missed_clockin_request(TEST_EMPLOYEE_ID, data)

        assert mock_db.rollback.called

    def test_submit_missed_clockin_already_clocked_in(self, attendance_service, mock_db):
        mock_emp = make_mock_employee()
        mock_db.get.return_value = mock_emp

        # Mock existing attendance with clock_in set
        existing_att = make_mock_attendance_record(clock_in=datetime.now(timezone.utc))
        mock_db.scalars.return_value.first.return_value = existing_att

        data = MissedClockinRequestCreate(
            attendance_date=date(2026, 7, 9),
            requested_clock_in=datetime.now(timezone.utc),
            reason="Forgot to mark login",
        )

        with pytest.raises(ValueError, match="already exists"):
            attendance_service.submit_missed_clockin_request(TEST_EMPLOYEE_ID, data)

    def test_submit_missed_clockin_future_time(self, attendance_service, mock_db):
        mock_emp = make_mock_employee()
        mock_db.get.return_value = mock_emp
        mock_db.scalars.return_value.first.return_value = None

        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        data = MissedClockinRequestCreate(
            attendance_date=date(2026, 7, 9),
            requested_clock_in=future_time,
            reason="Forgot to mark login",
        )

        with pytest.raises(ValueError, match="cannot be in the future"):
            attendance_service.submit_missed_clockin_request(TEST_EMPLOYEE_ID, data)

    # ── Approve Request ─────────────────────────────────────────────────────────

    def test_approve_missed_clockin_success(self, attendance_service, mock_db):
        reviewer_id = uuid.uuid4()
        attendance_service.current_user_id = reviewer_id

        req_time = datetime.now(timezone.utc) - timedelta(hours=2)
        req = MissedClockinRequest(
            id=uuid.uuid4(),
            employee_id=TEST_EMPLOYEE_ID,
            attendance_date=date(2026, 7, 9),
            requested_clock_in=req_time,
            reason="Forgot login",
            status="PENDING",
            created_at=datetime.now(timezone.utc),
        )
        req.employee = make_mock_employee(id=TEST_EMPLOYEE_ID)

        mock_db.get.return_value = req

        # Rule mock
        rule = AttendanceRule(
            office_start_time="09:00",
            office_end_time="18:00",
            late_mark_after_minutes=15,
            half_day_hours=4.0,
            overtime_threshold_hours=8.0,
        )

        # Mock db queries inside approve:
        # 1. select(ApprovalInstance.id) guard: no active engine-owned flow for this request
        # 2. select(AttendanceRule) to get rule_obj
        # 3. select(Attendance) in _get_or_create_record
        mock_db.scalars.return_value.first.side_effect = [
            None,  # Guard: no ApprovalInstance already tracking this request
            rule,  # Get rule
            None,  # Get existing attendance record (returns None, meaning create new)
        ]

        res = attendance_service.approve_missed_clockin_request(req.id, review_notes="Approved by admin")

        assert res.status == "APPROVED"
        assert res.reviewed_by == reviewer_id
        assert res.review_notes == "Approved by admin"
        assert mock_db.commit.called

    def test_approve_missed_clockin_self_approval_fails(self, attendance_service, mock_db):
        # Current user is the employee themselves
        attendance_service.current_user_id = TEST_EMPLOYEE_ID

        req = MissedClockinRequest(
            id=uuid.uuid4(),
            employee_id=TEST_EMPLOYEE_ID,
            attendance_date=date(2026, 7, 9),
            requested_clock_in=datetime.now(timezone.utc) - timedelta(hours=1),
            reason="Forgot login",
            status="PENDING",
            created_at=datetime.now(timezone.utc),
        )
        mock_db.get.return_value = req

        with pytest.raises(ValueError, match="cannot approve your own"):
            attendance_service.approve_missed_clockin_request(req.id)

    # ── Reject Request ──────────────────────────────────────────────────────────

    def test_reject_missed_clockin_success(self, attendance_service, mock_db):
        reviewer_id = uuid.uuid4()
        attendance_service.current_user_id = reviewer_id

        req = MissedClockinRequest(
            id=uuid.uuid4(),
            employee_id=TEST_EMPLOYEE_ID,
            attendance_date=date(2026, 7, 9),
            requested_clock_in=datetime.now(timezone.utc) - timedelta(hours=1),
            reason="Forgot login",
            status="PENDING",
            created_at=datetime.now(timezone.utc),
        )
        req.employee = make_mock_employee(id=TEST_EMPLOYEE_ID)

        mock_db.get.return_value = req
        # Guard: no ApprovalInstance already tracking this request
        mock_db.scalars.return_value.first.return_value = None

        res = attendance_service.reject_missed_clockin_request(req.id, review_notes="Rejected")

        assert res.status == "REJECTED"
        assert res.reviewed_by == reviewer_id
        assert res.review_notes == "Rejected"
        assert mock_db.commit.called
