"""
Unit tests for ProjectMetricsService computation logic.

These tests exercise each static helper and the main recalculate() method
using mock SQLAlchemy sessions — no real database required.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.services.project_metrics_service import ProjectMetricsService


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_task(
    status: str = "NOT_STARTED",
    estimated_hours: float = 10.0,
    actual_hours: float = 0.0,
    actual_start_date: date | None = None,
    actual_end_date: date | None = None,
) -> MagicMock:
    t = MagicMock()
    t.status = status
    t.estimated_hours = estimated_hours
    t.actual_hours = actual_hours
    t.actual_start_date = actual_start_date
    t.actual_end_date = actual_end_date
    return t


# ── _compute_estimated_hours ───────────────────────────────────────────────────

class TestComputeEstimatedHours:
    def test_empty_task_list(self):
        assert ProjectMetricsService._compute_estimated_hours([]) == 0.0

    def test_single_task(self):
        assert ProjectMetricsService._compute_estimated_hours([make_task(estimated_hours=8.0)]) == 8.0

    def test_multiple_tasks_summed(self):
        tasks = [make_task(estimated_hours=4.0), make_task(estimated_hours=6.5)]
        assert ProjectMetricsService._compute_estimated_hours(tasks) == 10.5

    def test_none_treated_as_zero(self):
        t = make_task()
        t.estimated_hours = None
        assert ProjectMetricsService._compute_estimated_hours([t]) == 0.0

    def test_result_rounded_to_two_decimals(self):
        tasks = [make_task(estimated_hours=1.005), make_task(estimated_hours=1.005)]
        result = ProjectMetricsService._compute_estimated_hours(tasks)
        assert result == round(2.01, 2)


# ── _compute_actual_hours ──────────────────────────────────────────────────────

class TestComputeActualHours:
    def test_empty_returns_zero(self):
        assert ProjectMetricsService._compute_actual_hours([]) == 0.0

    def test_sum_of_task_actual_hours(self):
        tasks = [make_task(actual_hours=3.0), make_task(actual_hours=2.5)]
        assert ProjectMetricsService._compute_actual_hours(tasks) == 5.5

    def test_none_actual_hours_treated_as_zero(self):
        t = make_task()
        t.actual_hours = None
        assert ProjectMetricsService._compute_actual_hours([t]) == 0.0


# ── _compute_actual_start ──────────────────────────────────────────────────────

class TestComputeActualStart:
    def test_no_tasks_returns_none(self):
        assert ProjectMetricsService._compute_actual_start([]) is None

    def test_returns_min_date(self):
        d1 = date(2026, 1, 10)
        d2 = date(2026, 1, 5)
        tasks = [make_task(actual_start_date=d1), make_task(actual_start_date=d2)]
        assert ProjectMetricsService._compute_actual_start(tasks) == d2

    def test_ignores_tasks_without_start_date(self):
        d = date(2026, 3, 1)
        tasks = [make_task(actual_start_date=None), make_task(actual_start_date=d)]
        assert ProjectMetricsService._compute_actual_start(tasks) == d

    def test_all_none_returns_none(self):
        tasks = [make_task(actual_start_date=None), make_task(actual_start_date=None)]
        assert ProjectMetricsService._compute_actual_start(tasks) is None


# ── _compute_actual_end ────────────────────────────────────────────────────────

class TestComputeActualEnd:
    def test_no_tasks_returns_none(self):
        assert ProjectMetricsService._compute_actual_end([]) is None

    def test_open_task_prevents_end_date(self):
        tasks = [
            make_task(status="COMPLETED", actual_end_date=date(2026, 6, 1)),
            make_task(status="IN_PROGRESS"),
        ]
        assert ProjectMetricsService._compute_actual_end(tasks) is None

    def test_all_completed_returns_max_date(self):
        tasks = [
            make_task(status="COMPLETED", actual_end_date=date(2026, 5, 1)),
            make_task(status="COMPLETED", actual_end_date=date(2026, 6, 15)),
        ]
        assert ProjectMetricsService._compute_actual_end(tasks) == date(2026, 6, 15)

    def test_all_cancelled_returns_max_date(self):
        tasks = [
            make_task(status="CANCELLED", actual_end_date=date(2026, 4, 1)),
            make_task(status="CANCELLED", actual_end_date=date(2026, 4, 10)),
        ]
        assert ProjectMetricsService._compute_actual_end(tasks) == date(2026, 4, 10)

    def test_mix_completed_and_cancelled_returns_max(self):
        tasks = [
            make_task(status="COMPLETED", actual_end_date=date(2026, 3, 1)),
            make_task(status="CANCELLED", actual_end_date=date(2026, 7, 1)),
        ]
        assert ProjectMetricsService._compute_actual_end(tasks) == date(2026, 7, 1)

    def test_all_closed_but_no_end_dates_returns_none(self):
        tasks = [
            make_task(status="COMPLETED", actual_end_date=None),
            make_task(status="CANCELLED", actual_end_date=None),
        ]
        assert ProjectMetricsService._compute_actual_end(tasks) is None


# ── _compute_progress ──────────────────────────────────────────────────────────

class TestComputeProgress:
    def test_no_tasks_returns_zero(self):
        assert ProjectMetricsService._compute_progress([]) == 0.0

    def test_no_completed_tasks(self):
        tasks = [make_task(status="IN_PROGRESS", estimated_hours=10.0)]
        assert ProjectMetricsService._compute_progress(tasks) == 0.0

    def test_all_completed(self):
        tasks = [
            make_task(status="COMPLETED", estimated_hours=5.0),
            make_task(status="COMPLETED", estimated_hours=5.0),
        ]
        assert ProjectMetricsService._compute_progress(tasks) == 100.0

    def test_half_completed_by_hours(self):
        tasks = [
            make_task(status="COMPLETED", estimated_hours=10.0),
            make_task(status="IN_PROGRESS", estimated_hours=10.0),
        ]
        assert ProjectMetricsService._compute_progress(tasks) == 50.0

    def test_weighted_by_estimated_hours(self):
        # 20h done out of 40h total = 50%; but 20h task is completed (est=20), 20h not (est=20)
        tasks = [
            make_task(status="COMPLETED", estimated_hours=20.0),
            make_task(status="NOT_STARTED", estimated_hours=20.0),
        ]
        assert ProjectMetricsService._compute_progress(tasks) == 50.0

    def test_zero_estimated_hours_returns_zero(self):
        tasks = [make_task(status="COMPLETED", estimated_hours=0.0)]
        assert ProjectMetricsService._compute_progress(tasks) == 0.0

    def test_cancelled_tasks_not_counted_in_completed(self):
        tasks = [
            make_task(status="CANCELLED", estimated_hours=10.0),
            make_task(status="IN_PROGRESS", estimated_hours=10.0),
        ]
        assert ProjectMetricsService._compute_progress(tasks) == 0.0


# ── _compute_status ────────────────────────────────────────────────────────────

class TestComputeStatus:
    def test_no_tasks_yields_yet_to_start(self):
        assert ProjectMetricsService._compute_status([]) == "Yet To Start"

    def test_any_in_progress_yields_in_progress(self):
        tasks = [
            make_task(status="IN_PROGRESS"),
            make_task(status="COMPLETED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "In Progress"

    def test_reopened_yields_in_progress(self):
        tasks = [
            make_task(status="REOPENED"),
            make_task(status="COMPLETED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "In Progress"

    def test_in_progress_beats_on_hold(self):
        tasks = [
            make_task(status="IN_PROGRESS"),
            make_task(status="ON_HOLD"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "In Progress"

    def test_on_hold_when_nothing_active(self):
        tasks = [
            make_task(status="ON_HOLD"),
            make_task(status="NOT_STARTED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "On Hold"

    def test_all_completed_yields_completed(self):
        tasks = [
            make_task(status="COMPLETED"),
            make_task(status="COMPLETED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "Completed"

    def test_mix_completed_and_cancelled_yields_completed(self):
        tasks = [
            make_task(status="COMPLETED"),
            make_task(status="CANCELLED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "Completed"

    def test_all_cancelled_yields_cancelled(self):
        tasks = [
            make_task(status="CANCELLED"),
            make_task(status="CANCELLED"),
        ]
        assert ProjectMetricsService._compute_status(tasks) == "Cancelled"

    def test_not_started_only_yields_yet_to_start(self):
        tasks = [make_task(status="NOT_STARTED"), make_task(status="NOT_STARTED")]
        assert ProjectMetricsService._compute_status(tasks) == "Yet To Start"

    def test_in_progress_beats_reopened(self):
        # Both map to "In Progress", but IN_PROGRESS has higher priority in the list
        tasks = [make_task(status="IN_PROGRESS"), make_task(status="REOPENED")]
        assert ProjectMetricsService._compute_status(tasks) == "In Progress"


# ── recalculate() integration ──────────────────────────────────────────────────

class TestRecalculate:
    def _make_project(self, **kwargs):
        p = MagicMock()
        p.id = UUID("44444444-4444-4444-8444-444444444444")
        p.is_active = True
        p.estimated_hours = kwargs.get("estimated_hours", 0.0)
        p.actual_hours = kwargs.get("actual_hours", 0.0)
        p.actual_start_date = kwargs.get("actual_start_date", None)
        p.actual_end_date = kwargs.get("actual_end_date", None)
        p.progress = kwargs.get("progress", 0.0)
        p.status = kwargs.get("status", "Yet To Start")
        return p

    def test_inactive_project_returns_empty(self):
        db = MagicMock()
        project = self._make_project()
        project.is_active = False
        db.get.return_value = project

        result = ProjectMetricsService.recalculate(db, project.id)
        assert result == {}

    def test_not_found_project_returns_empty(self):
        db = MagicMock()
        db.get.return_value = None

        result = ProjectMetricsService.recalculate(db, UUID("00000000-0000-4000-8000-000000000000"))
        assert result == {}

    def test_no_tasks_sets_yet_to_start(self):
        db = MagicMock()
        project = self._make_project()
        db.get.return_value = project
        db.scalars.return_value.all.return_value = []

        with patch("app.services.project_metrics_service.AuditService"):
            result = ProjectMetricsService.recalculate(db, project.id)

        assert result["new"]["status"] == "Yet To Start"
        assert result["new"]["estimated_hours"] == 0.0
        assert result["new"]["progress"] == 0.0

    def test_task_in_progress_updates_project_status(self):
        db = MagicMock()
        project = self._make_project(status="Yet To Start")
        db.get.return_value = project

        task = make_task(status="IN_PROGRESS", estimated_hours=10.0, actual_hours=3.0,
                         actual_start_date=date(2026, 1, 1))
        db.scalars.return_value.all.return_value = [task]

        with patch("app.services.project_metrics_service.AuditService"):
            result = ProjectMetricsService.recalculate(db, project.id)

        assert result["new"]["status"] == "In Progress"
        assert result["new"]["estimated_hours"] == 10.0
        assert result["new"]["actual_hours"] == 3.0
        assert result["new"]["actual_start_date"] == str(date(2026, 1, 1))
        assert result["new"]["actual_end_date"] is None

    def test_all_tasks_completed_sets_completed_and_end_date(self):
        db = MagicMock()
        project = self._make_project()
        db.get.return_value = project

        t1 = make_task(status="COMPLETED", estimated_hours=5.0, actual_end_date=date(2026, 6, 1))
        t2 = make_task(status="COMPLETED", estimated_hours=5.0, actual_end_date=date(2026, 6, 15))
        db.scalars.return_value.all.return_value = [t1, t2]

        with patch("app.services.project_metrics_service.AuditService"):
            result = ProjectMetricsService.recalculate(db, project.id)

        assert result["new"]["status"] == "Completed"
        assert result["new"]["progress"] == 100.0
        assert result["new"]["actual_end_date"] == str(date(2026, 6, 15))

    def test_flush_called_once(self):
        db = MagicMock()
        project = self._make_project()
        db.get.return_value = project
        db.scalars.return_value.all.return_value = []

        with patch("app.services.project_metrics_service.AuditService"):
            ProjectMetricsService.recalculate(db, project.id)

        db.flush.assert_called_once()

    def test_audit_log_only_on_change(self):
        db = MagicMock()
        # Project already matches what recalc would compute
        project = self._make_project(status="Yet To Start", estimated_hours=0.0,
                                     actual_hours=0.0, progress=0.0)
        db.get.return_value = project
        db.scalars.return_value.all.return_value = []

        with patch("app.services.project_metrics_service.AuditService") as mock_audit:
            ProjectMetricsService.recalculate(db, project.id)

        # No change → audit.log should NOT have been called
        mock_audit.log.assert_not_called()
