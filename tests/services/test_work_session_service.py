from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.task_work_session import TaskWorkSession

from tests.conftest import (
    TEST_BREAK_ID,
    TEST_EMPLOYEE_ID,
    TEST_OTHER_USER_ID,
    TEST_PROJECT_ID,
    TEST_SESSION_ID,
    TEST_TASK_ID,
    make_mock_attendance,
    make_mock_employee,
    make_mock_project,
    make_mock_task,
    make_mock_task_assignment,
    make_mock_task_work_session,
)


# ── Start Session ─────────────────────────────────────────────────────────────


class TestStartSession:
    def test_starts_session_successfully(self, work_session_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(status="NOT_STARTED")
        mock_proj = make_mock_project()
        mock_att = make_mock_attendance(clock_out=None)
        mock_assignment = make_mock_task_assignment()

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        mock_db.scalar.side_effect = [
            0,  # overlapping check
            None,  # existing active session
            mock_att,  # attendance check
            mock_assignment,  # assignment check
        ]

        result = work_session_service.start_session(
            task_id=TEST_TASK_ID,
            project_id=TEST_PROJECT_ID,
            session_type="REGULAR",
        )

        assert result is not None
        assert result.status == "RUNNING"
        assert result.task_id == TEST_TASK_ID
        assert mock_db.add.called
        assert mock_db.commit.called

    def test_raises_on_overlapping_session(self, work_session_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(status="IN_PROGRESS")
        mock_proj = make_mock_project()

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        mock_db.scalar.side_effect = [
            1,  # overlapping check fails
        ]

        with pytest.raises(ValueError, match="already have an active"):
            work_session_service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_raises_if_not_clocked_in(self, work_session_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(status="IN_PROGRESS")
        mock_proj = make_mock_project()

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        mock_db.scalar.side_effect = [
            0,  # no overlapping
            None,  # no existing active session
            None,  # no attendance
        ]

        with pytest.raises(ValueError, match="clocked in"):
            work_session_service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_raises_if_no_assignment(self, work_session_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(status="IN_PROGRESS")
        mock_proj = make_mock_project()
        mock_att = make_mock_attendance(clock_out=None)

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        mock_db.scalar.side_effect = [
            0,  # no overlapping
            None,  # no existing active
            mock_att,  # attendance ok
            None,  # no assignment
        ]

        with pytest.raises(ValueError, match="not assigned"):
            work_session_service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_raises_on_inactive_task(self, work_session_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(is_active=False)
        mock_proj = make_mock_project()

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        mock_db.scalar.return_value = 0

        with pytest.raises(ValueError, match="inactive task"):
            work_session_service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_raises_if_not_found(self, work_session_service, mock_db):
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            work_session_service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.work_session_service import WorkSessionService

        service = WorkSessionService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.start_session(
                task_id=TEST_TASK_ID,
                project_id=TEST_PROJECT_ID,
            )

    def test_auto_pauses_existing_session(self, work_session_service, mock_db):
        from datetime import datetime, timezone, timedelta
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(status="IN_PROGRESS")
        mock_proj = make_mock_project()
        mock_att = make_mock_attendance(clock_out=None)
        mock_assignment = make_mock_task_assignment()

        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        existing_session = make_mock_task_work_session(
            status="RUNNING", duration_minutes=10, start_time=past
        )
        mock_db.scalar.side_effect = [
            0,  # no overlapping
            existing_session,  # existing active session
            mock_att,  # attendance ok
            mock_assignment,  # assignment ok
        ]

        result = work_session_service.start_session(
            task_id=TEST_TASK_ID,
            project_id=TEST_PROJECT_ID,
        )

        assert existing_session.status == "PAUSED"
        assert existing_session.duration_minutes > 10
        assert result.status == "RUNNING"
        assert mock_db.commit.called


# ── Pause Session ──────────────────────────────────────────────────────────────


class TestPauseSession:
    def test_pauses_running_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_db.get.return_value = session

        result = work_session_service.pause_session(TEST_SESSION_ID, reason="Break time")

        assert result.status == "PAUSED"
        assert mock_db.commit.called

    def test_raises_on_non_running_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="COMPLETED")
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="Only RUNNING sessions can be paused"):
            work_session_service.pause_session(TEST_SESSION_ID)

    def test_raises_if_not_owner(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING", employee_id=TEST_OTHER_USER_ID)
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="only pause your own"):
            work_session_service.pause_session(TEST_SESSION_ID)

    def test_raises_if_not_found(self, work_session_service, mock_db):
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            work_session_service.pause_session(TEST_SESSION_ID)


# ── Resume Session ────────────────────────────────────────────────────────────


class TestResumeSession:
    def test_resumes_paused_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="PAUSED")
        mock_db.get.return_value = session
        mock_db.scalar.return_value = None  # no other running session

        result = work_session_service.resume_session(TEST_SESSION_ID)

        assert result.status == "RUNNING"
        assert mock_db.commit.called

    def test_raises_if_not_paused(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="Only PAUSED sessions can be resumed"):
            work_session_service.resume_session(TEST_SESSION_ID)

    def test_raises_if_other_running_exists(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="PAUSED")
        mock_db.get.return_value = session
        mock_db.scalar.return_value = make_mock_task_work_session(status="RUNNING")

        with pytest.raises(ValueError, match="already have a running session"):
            work_session_service.resume_session(TEST_SESSION_ID)

    def test_raises_if_not_owner(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="PAUSED", employee_id=TEST_OTHER_USER_ID)
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="only resume your own"):
            work_session_service.resume_session(TEST_SESSION_ID)


# ── Complete Session ──────────────────────────────────────────────────────────


class TestCompleteSession:
    def test_completes_running_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_proj = make_mock_project()
        mock_task = make_mock_task()

        mock_db.get.side_effect = lambda model, id: {
            TaskWorkSession: session,
            Project: mock_proj,
            Task: mock_task,
        }.get(model)

        mock_db.scalar.return_value = 60  # total minutes for _recompute

        result = work_session_service.complete_session(TEST_SESSION_ID)

        assert result.status == "COMPLETED"
        assert mock_db.commit.called

    def test_raises_if_already_completed(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="COMPLETED")
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="Only RUNNING or PAUSED"):
            work_session_service.complete_session(TEST_SESSION_ID)

    def test_raises_if_not_owner(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING", employee_id=TEST_OTHER_USER_ID)
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="only complete your own"):
            work_session_service.complete_session(TEST_SESSION_ID)


# ── Cancel Session ────────────────────────────────────────────────────────────


class TestCancelSession:
    def test_cancels_running_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_db.get.return_value = session

        result = work_session_service.cancel_session(TEST_SESSION_ID)

        assert result.status == "CANCELLED"
        assert mock_db.commit.called

    def test_raises_if_already_cancelled(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="COMPLETED")
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="Only RUNNING or PAUSED"):
            work_session_service.cancel_session(TEST_SESSION_ID)

    def test_raises_if_not_owner(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING", employee_id=TEST_OTHER_USER_ID)
        mock_db.get.return_value = session

        with pytest.raises(ValueError, match="only cancel your own"):
            work_session_service.cancel_session(TEST_SESSION_ID)


# ── Get Active Session ────────────────────────────────────────────────────────


class TestGetActiveSession:
    def test_returns_active_session(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_db.scalar.return_value = session

        result = work_session_service.get_active_session()

        assert result is not None
        assert result.id == TEST_SESSION_ID
        assert result.elapsed_minutes >= 0

    def test_returns_none_if_no_active(self, work_session_service, mock_db):
        mock_db.scalar.return_value = None

        result = work_session_service.get_active_session()

        assert result is None

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.work_session_service import WorkSessionService

        service = WorkSessionService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.get_active_session()


# ── My Sessions ────────────────────────────────────────────────────────────────


class TestGetMySessions:
    def test_returns_sessions(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="COMPLETED")
        mock_db.scalars.return_value.all.return_value = [session]
        mock_db.scalar.return_value = 1

        results, total = work_session_service.get_my_sessions()

        assert total == 1
        assert len(results) == 1
        assert results[0].id == TEST_SESSION_ID

    def test_respects_status_filter(self, work_session_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []
        mock_db.scalar.return_value = 0

        results, total = work_session_service.get_my_sessions(status="RUNNING")

        assert total == 0
        assert len(results) == 0

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.work_session_service import WorkSessionService

        service = WorkSessionService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.get_my_sessions()


# ── Task Sessions ──────────────────────────────────────────────────────────────


class TestGetTaskSessions:
    def test_returns_task_sessions(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="COMPLETED")
        mock_db.scalars.return_value.all.return_value = [session]

        results = work_session_service.get_task_sessions(TEST_TASK_ID)

        assert len(results) == 1
        assert results[0].task_id == TEST_TASK_ID


# ── Daily Summary ──────────────────────────────────────────────────────────────


class TestGetDailySummary:
    def test_returns_summary(self, work_session_service, mock_db):
        session = make_mock_task_work_session(
            status="COMPLETED", duration_minutes=120
        )

        def scalar_side_effect(*args, **kwargs):
            return [session]

        mock_db.scalars.return_value.all.side_effect = [
            [session],  # sessions query
            [],  # breaks query
        ]
        mock_db.scalar.return_value = None

        result = work_session_service.get_daily_summary()

        assert result.total_session_minutes >= 120
        assert result.total_break_minutes == 0
        assert result.session_count == 1

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.work_session_service import WorkSessionService

        service = WorkSessionService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.get_daily_summary()


# ── Running Sessions (Rule 11) ─────────────────────────────────────────────────


class TestGetRunningSessions:
    def test_returns_running_sessions(self, work_session_service, mock_db):
        session = make_mock_task_work_session(status="RUNNING")
        mock_db.scalars.return_value.all.return_value = [session]

        results = work_session_service.get_running_sessions()

        assert len(results) == 1
        assert results[0].elapsed_minutes >= 0

    def test_returns_empty_list(self, work_session_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []

        results = work_session_service.get_running_sessions()

        assert len(results) == 0


# ── Clock-out Auto-close (Rule 7) ─────────────────────────────────────────────


class TestEndCurrentSessionOnClockOut:
    def test_ends_session(self, work_session_service, mock_db):
        from datetime import datetime, timezone, timedelta
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        session = make_mock_task_work_session(status="RUNNING", start_time=past)
        mock_db.scalar.return_value = session

        result = work_session_service.end_current_session_on_clock_out()

        assert session.status == "ABANDONED"
        assert session.duration_minutes > 0
        assert result is not None

    def test_returns_none_if_no_session(self, work_session_service, mock_db):
        mock_db.scalar.return_value = None

        result = work_session_service.end_current_session_on_clock_out()

        assert result is None

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.work_session_service import WorkSessionService

        service = WorkSessionService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.end_current_session_on_clock_out()


# ── All Sessions (Admin) ───────────────────────────────────────────────────────


class TestGetAllSessions:
    def test_returns_all_sessions(self, work_session_service, mock_db):
        session = make_mock_task_work_session()
        mock_db.scalars.return_value.all.return_value = [session]
        mock_db.scalar.return_value = 1

        results, total = work_session_service.get_all_sessions()

        assert total == 1
        assert len(results) == 1

    def test_filters_by_employee(self, work_session_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []
        mock_db.scalar.return_value = 0

        results, total = work_session_service.get_all_sessions(
            employee_id=TEST_EMPLOYEE_ID
        )

        assert total == 0
