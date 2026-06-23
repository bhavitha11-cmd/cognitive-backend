from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.employee_break import EmployeeBreak
from app.models.task_work_session import TaskWorkSession

from tests.conftest import (
    TEST_BREAK_ID,
    TEST_EMPLOYEE_ID,
    TEST_OTHER_USER_ID,
    TEST_SESSION_ID,
    TEST_TASK_ID,
    make_mock_attendance,
    make_mock_employee,
    make_mock_employee_break,
    make_mock_task_work_session,
)


# ── Start Break ────────────────────────────────────────────────────────────────


class TestStartBreak:
    def test_starts_break_successfully(self, break_service, mock_db):
        mock_emp = make_mock_employee()
        mock_att = make_mock_attendance(clock_out=None)

        mock_db.get.return_value = mock_emp
        mock_db.scalar.side_effect = [
            mock_att,  # attendance ok
            None,  # no active break
            None,  # no running session
        ]

        result = break_service.start_break(remarks="Lunch break")

        assert result is not None
        assert result.employee_id == TEST_EMPLOYEE_ID
        assert mock_db.add.called
        assert mock_db.commit.called

    def test_raises_on_missing_attendance(self, break_service, mock_db):
        mock_emp = make_mock_employee()

        mock_db.get.return_value = mock_emp
        mock_db.scalar.side_effect = [
            None,  # no attendance
        ]

        with pytest.raises(ValueError, match="clocked in"):
            break_service.start_break()

    def test_raises_on_active_break(self, break_service, mock_db):
        mock_emp = make_mock_employee()
        mock_att = make_mock_attendance(clock_out=None)
        active_break = make_mock_employee_break(break_end=None)

        mock_db.get.return_value = mock_emp
        mock_db.scalar.side_effect = [
            mock_att,  # attendance ok
            active_break,  # already has active break
        ]

        with pytest.raises(ValueError, match="already have an active break"):
            break_service.start_break()

    def test_raises_on_missing_employee(self, break_service, mock_db):
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            break_service.start_break()

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.break_service import BreakService

        service = BreakService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.start_break()

    def test_auto_pauses_running_session(self, break_service, mock_db):
        mock_emp = make_mock_employee()
        mock_att = make_mock_attendance(clock_out=None)
        running_session = make_mock_task_work_session(status="RUNNING")

        mock_db.get.return_value = mock_emp
        mock_db.scalar.side_effect = [
            mock_att,  # attendance ok
            None,  # no active break
            running_session,  # running session found
        ]

        result = break_service.start_break()

        assert running_session.status == "PAUSED"
        assert result is not None
        assert mock_db.commit.called


# ── End Break ──────────────────────────────────────────────────────────────────


class TestEndBreak:
    def test_ends_break_successfully(self, break_service, mock_db):
        from datetime import datetime, timezone, timedelta
        past = datetime.now(timezone.utc) - timedelta(minutes=30)
        active_break = make_mock_employee_break(break_end=None, break_start=past)

        mock_db.scalar.side_effect = [
            active_break,  # active break found
            None,  # no paused session
        ]

        result = break_service.end_break(remarks="Back from lunch")

        assert result is not None
        assert result.duration_minutes >= 29
        assert mock_db.commit.called

    def test_raises_if_no_active_break(self, break_service, mock_db):
        mock_db.scalar.return_value = None

        with pytest.raises(ValueError, match="No active break"):
            break_service.end_break()

    def test_resumes_paused_session(self, break_service, mock_db):
        from datetime import datetime, timezone, timedelta
        past = datetime.now(timezone.utc) - timedelta(minutes=15)
        active_break = make_mock_employee_break(break_end=None, break_start=past)
        paused_session = make_mock_task_work_session(
            status="PAUSED",
            pause_reason="Auto-paused: break started",
        )

        mock_db.scalar.side_effect = [
            active_break,  # active break found
            paused_session,  # paused session found
        ]

        result = break_service.end_break()

        assert paused_session.status == "RUNNING"
        assert result.duration_minutes >= 14
        assert mock_db.commit.called

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.break_service import BreakService

        service = BreakService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.end_break()


# ── Get Active Break ──────────────────────────────────────────────────────────


class TestGetActiveBreak:
    def test_returns_active_break(self, break_service, mock_db):
        active_break = make_mock_employee_break(break_end=None)
        mock_db.scalar.return_value = active_break

        result = break_service.get_active_break()

        assert result is not None
        assert result.id == TEST_BREAK_ID

    def test_returns_none_if_no_break(self, break_service, mock_db):
        mock_db.scalar.return_value = None

        result = break_service.get_active_break()

        assert result is None

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.break_service import BreakService

        service = BreakService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.get_active_break()


# ── Get My Breaks ──────────────────────────────────────────────────────────────


class TestGetMyBreaks:
    def test_returns_breaks(self, break_service, mock_db):
        brk = make_mock_employee_break()
        mock_db.scalars.return_value.all.return_value = [brk]
        mock_db.scalar.return_value = 1

        results, total = break_service.get_my_breaks()

        assert total == 1
        assert len(results) == 1
        assert results[0].id == TEST_BREAK_ID

    def test_returns_empty(self, break_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []
        mock_db.scalar.return_value = 0

        results, total = break_service.get_my_breaks()

        assert total == 0
        assert len(results) == 0

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.break_service import BreakService

        service = BreakService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.get_my_breaks()
