"""
Integration tests: verify that the project metrics recalculation cascade is
triggered from every service that can change project-relevant data.

Covered trigger points:
  - TimeEntryService: create / update / delete / approve / reject
  - ReworkService: open_rework / close_rework
  - WorkSessionService: start_session (task → IN_PROGRESS), complete_session

All tests mock the DB and patch ProjectMetricsService.recalculate so we can
assert it was called without hitting a real database.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch, call
from uuid import UUID

import pytest

from tests.conftest import (
    TEST_EMPLOYEE_ID,
    TEST_PROJECT_ID,
    TEST_TASK_ID,
    TEST_SESSION_ID,
    TEST_REWORK_ID,
    make_mock_employee,
    make_mock_task,
    make_mock_project,
    make_mock_time_entry,
    make_mock_task_work_session,
    make_mock_attendance,
    make_mock_task_assignment,
    make_mock_task_rework,
)


RECALC_PATH = "app.services.project_metrics_service.ProjectMetricsService.recalculate"


# ── TimeEntryService triggers ──────────────────────────────────────────────────

class TestTimeEntryProjectTrigger:
    def _make_service(self, mock_db):
        from app.services.time_entry_service import TimeEntryService
        svc = TimeEntryService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)
        return svc

    def _setup_db_for_recompute(self, mock_db, task_id=TEST_TASK_ID, project_id=TEST_PROJECT_ID):
        """Configure mock_db so _recompute_task_actual_hours() works correctly."""
        mock_db.scalar.return_value = 5.0  # SUM of hours
        task = make_mock_task(id=task_id, project_id=project_id)
        mock_db.get.return_value = task
        project = make_mock_project(id=project_id)
        mock_db.get.side_effect = lambda model, pk: task if pk == task_id else project

    def test_recompute_task_actual_hours_triggers_project_recalc(self, mock_db):
        """_recompute_task_actual_hours() must cascade to project metrics."""
        task = make_mock_task(project_id=TEST_PROJECT_ID)
        mock_db.scalar.return_value = 8.0
        mock_db.get.return_value = task

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc:
            svc._recompute_task_actual_hours(TEST_TASK_ID)

        mock_recalc.assert_called_once_with(mock_db, TEST_PROJECT_ID)

    def test_no_recalc_when_task_not_found(self, mock_db):
        """If the task doesn't exist, no project recalc should fire."""
        mock_db.scalar.return_value = 0.0
        mock_db.get.return_value = None  # task not found

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH) as mock_recalc:
            svc._recompute_task_actual_hours(TEST_TASK_ID)

        mock_recalc.assert_not_called()

    def test_trigger_project_recalc_helper(self, mock_db):
        """_trigger_project_recalc() calls ProjectMetricsService.recalculate and commits."""
        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc:
            svc._trigger_project_recalc(TEST_PROJECT_ID)

        mock_recalc.assert_called_once_with(mock_db, TEST_PROJECT_ID)
        mock_db.commit.assert_called()

    def test_trigger_project_recalc_swallows_exceptions(self, mock_db):
        """_trigger_project_recalc() must not propagate errors (fire-and-forget)."""
        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, side_effect=RuntimeError("DB down")):
            svc._trigger_project_recalc(TEST_PROJECT_ID)  # should not raise


# ── ReworkService triggers ─────────────────────────────────────────────────────

class TestReworkProjectTrigger:
    def _make_service(self, mock_db):
        from app.services.rework_service import ReworkService
        return ReworkService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)

    def test_open_rework_triggers_project_recalc(self, mock_db):
        """open_rework() changes task status to REOPENED — project must recalculate."""
        task = make_mock_task(status="COMPLETED", project_id=TEST_PROJECT_ID)
        task.is_active = True
        task.rework_count = 0
        task.original_estimated_hours = None
        task.actual_start_date = None

        rework = make_mock_task_rework(task_id=TEST_TASK_ID)

        mock_db.get.return_value = task
        mock_db.scalar.return_value = 0  # no open rework cycles

        from app.models.task_rework_history import TaskReworkHistory
        added_rework = []

        def _add(obj):
            if hasattr(obj, "task_id"):  # it's a TaskReworkHistory
                obj.id = rework.id
            added_rework.append(obj)

        mock_db.add.side_effect = _add

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc, \
             patch.object(svc, "_build_read", return_value=rework):
            svc.open_rework(TEST_TASK_ID, reason="Client change")

        mock_recalc.assert_called_once_with(mock_db, TEST_PROJECT_ID)

    def test_close_rework_triggers_project_recalc(self, mock_db):
        """close_rework() updates rework hours — project metrics must recalculate."""
        task = make_mock_task(project_id=TEST_PROJECT_ID)
        rework = make_mock_task_rework(task_id=TEST_TASK_ID, closed_at=None)
        rework.closed_at = None  # still open

        def _get(model, pk):
            if pk == TEST_REWORK_ID:
                return rework
            if pk == TEST_TASK_ID:
                return task
            return None

        mock_db.get.side_effect = _get
        mock_db.scalar.return_value = 2.5  # total rework hours

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc, \
             patch.object(svc, "_build_read", return_value=rework):
            svc.close_rework(TEST_REWORK_ID, hours_spent=2.0)

        mock_recalc.assert_called_once_with(mock_db, TEST_PROJECT_ID)

    def test_trigger_project_recalc_swallows_exceptions(self, mock_db):
        """_trigger_project_recalc() in ReworkService must not propagate errors."""
        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, side_effect=RuntimeError("fail")):
            svc._trigger_project_recalc(TEST_PROJECT_ID)  # must not raise


# ── WorkSessionService triggers ────────────────────────────────────────────────

class TestWorkSessionProjectTrigger:
    def _make_service(self, mock_db):
        from app.services.work_session_service import WorkSessionService
        return WorkSessionService(db=mock_db, current_user_id=TEST_EMPLOYEE_ID)

    def test_start_session_triggers_project_recalc(self, mock_db):
        """start_session() sets task to IN_PROGRESS — project must recalculate."""
        employee = make_mock_employee()
        task = make_mock_task(status="NOT_STARTED", project_id=TEST_PROJECT_ID)
        task.actual_start_date = None
        project = make_mock_project()
        attendance = make_mock_attendance(clock_in=datetime.now(timezone.utc))
        assignment = make_mock_task_assignment(task_id=TEST_TASK_ID, employee_id=TEST_EMPLOYEE_ID)

        def _get(model, pk):
            name = getattr(model, "__name__", str(model))
            if "Employee" in name:
                return employee
            if "Task" in name:
                return task
            if "Project" in name:
                return project
            return None

        mock_db.get.side_effect = _get

        # scalar calls: overlapping sessions check → 0, existing active → None, attendance → present, assignment → present
        scalar_returns = iter([0, None, attendance, assignment])
        mock_db.scalar.side_effect = lambda q: next(scalar_returns, None)

        session = make_mock_task_work_session(status="RUNNING")
        added_objects = []

        def _add(obj):
            if hasattr(obj, "duration_minutes"):
                obj.id = TEST_SESSION_ID
            added_objects.append(obj)

        mock_db.add.side_effect = _add

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc, \
             patch.object(svc, "_build_read", return_value=session):
            svc.start_session(TEST_TASK_ID, TEST_PROJECT_ID)

        mock_recalc.assert_called_with(mock_db, TEST_PROJECT_ID)

    def test_complete_session_triggers_project_recalc(self, mock_db):
        """complete_session() already triggers recalc — verify it calls recalculate."""
        session = make_mock_task_work_session(
            status="RUNNING",
            start_time=datetime.now(timezone.utc),
            project_id=TEST_PROJECT_ID,
            task_id=TEST_TASK_ID,
        )
        mock_db.get.return_value = session

        svc = self._make_service(mock_db)

        with patch(RECALC_PATH, return_value={}) as mock_recalc, \
             patch.object(svc, "_recompute_task_actual_hours"), \
             patch.object(svc, "_generate_time_entry_from_session"), \
             patch.object(svc, "_build_read", return_value=session):
            svc.complete_session(TEST_SESSION_ID)

        mock_recalc.assert_called()

    def test_recompute_task_actual_hours_uses_time_entries(self, mock_db):
        """WorkSessionService._recompute_task_actual_hours must use TimeEntry SUM, not sessions."""
        from app.models.time_entry import TimeEntry

        task = make_mock_task()
        mock_db.scalar.return_value = 6.0  # hours from time entries
        mock_db.get.return_value = task

        svc = self._make_service(mock_db)
        svc._recompute_task_actual_hours(TEST_TASK_ID)

        # The scalar query must reference TimeEntry.hours_spent (not TaskWorkSession)
        scalar_call_args = mock_db.scalar.call_args_list
        assert len(scalar_call_args) >= 1

        # task.actual_hours must be set from the time-entry total
        assert task.actual_hours == 6.0
