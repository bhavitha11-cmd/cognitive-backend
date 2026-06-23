from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.models.employee import Employee
from app.models.task import Task
from app.models.task_rework_history import TaskReworkHistory

from tests.conftest import (
    TEST_EMPLOYEE_ID,
    TEST_OTHER_USER_ID,
    TEST_REWORK_ID,
    TEST_TASK_ID,
    make_mock_employee,
    make_mock_task,
    make_mock_task_rework,
)


# ── Open Rework ────────────────────────────────────────────────────────────────


class TestOpenRework:
    def test_opens_rework_successfully(self, rework_service, mock_db):
        mock_task = make_mock_task(status="COMPLETED", rework_count=0)
        mock_db.get.return_value = mock_task
        mock_db.scalar.return_value = 0  # no open rework cycles

        result = rework_service.open_rework(
            task_id=TEST_TASK_ID,
            reason="Client requested changes",
        )

        assert result is not None
        assert result.rework_number == 1
        assert mock_task.status == "REOPENED"
        assert mock_task.rework_count == 1
        assert mock_db.add.called
        assert mock_db.commit.called

    def test_raises_if_already_open_rework(self, rework_service, mock_db):
        mock_task = make_mock_task(status="REOPENED", rework_count=1)
        mock_db.get.return_value = mock_task
        mock_db.scalar.return_value = 1  # already open

        with pytest.raises(ValueError, match="already has an open rework"):
            rework_service.open_rework(task_id=TEST_TASK_ID)

    def test_raises_on_inactive_task(self, rework_service, mock_db):
        mock_task = make_mock_task(is_active=False)
        mock_db.get.return_value = mock_task

        with pytest.raises(ValueError, match="inactive task"):
            rework_service.open_rework(task_id=TEST_TASK_ID)

    def test_raises_on_missing_task(self, rework_service, mock_db):
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            rework_service.open_rework(task_id=TEST_TASK_ID)

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.rework_service import ReworkService

        service = ReworkService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.open_rework(task_id=TEST_TASK_ID)


# ── Close Rework ───────────────────────────────────────────────────────────────


class TestCloseRework:
    def test_closes_rework_successfully(self, rework_service, mock_db):
        mock_rework = make_mock_task_rework(closed_at=None)
        mock_task = make_mock_task()

        def mock_get(model, id_val):
            if model == TaskReworkHistory and id_val == TEST_REWORK_ID:
                return mock_rework
            if model == Task and id_val == TEST_TASK_ID:
                return mock_task
            return None

        mock_db.get.side_effect = mock_get
        mock_db.scalar.return_value = 5.0  # total rework hours

        result = rework_service.close_rework(
            rework_id=TEST_REWORK_ID,
            hours_spent=5.0,
        )

        assert result is not None
        assert result.hours_spent == 5.0
        assert mock_task.total_rework_hours == 5.0
        assert mock_db.commit.called

    def test_raises_if_already_closed(self, rework_service, mock_db):
        mock_rework = make_mock_task_rework(closed_at=datetime.now(timezone.utc))
        mock_db.get.return_value = mock_rework

        with pytest.raises(ValueError, match="already closed"):
            rework_service.close_rework(
                rework_id=TEST_REWORK_ID,
                hours_spent=3.0,
            )

    def test_raises_on_missing_rework(self, rework_service, mock_db):
        mock_db.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            rework_service.close_rework(
                rework_id=TEST_REWORK_ID,
                hours_spent=2.0,
            )

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.rework_service import ReworkService

        service = ReworkService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.close_rework(
                rework_id=TEST_REWORK_ID,
                hours_spent=1.0,
            )


# ── Get Rework History ─────────────────────────────────────────────────────────


class TestGetReworkHistory:
    def test_returns_history(self, rework_service, mock_db):
        rw1 = make_mock_task_rework(rework_number=1)
        rw2 = make_mock_task_rework(rework_number=2)
        mock_db.scalars.return_value.all.return_value = [rw1, rw2]

        results = rework_service.get_task_rework_history(TEST_TASK_ID)

        assert len(results) == 2
        assert results[0].rework_number == 1

    def test_returns_empty(self, rework_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []

        results = rework_service.get_task_rework_history(TEST_TASK_ID)

        assert len(results) == 0


# ── Get Open Rework Cycles ─────────────────────────────────────────────────────


class TestGetOpenReworkCycles:
    def test_returns_open_cycles(self, rework_service, mock_db):
        rw = make_mock_task_rework(closed_at=None)
        mock_db.scalars.return_value.all.return_value = [rw]

        results = rework_service.get_open_rework_cycles()

        assert len(results) == 1
        assert results[0].closed_at is None

    def test_returns_empty(self, rework_service, mock_db):
        mock_db.scalars.return_value.all.return_value = []

        results = rework_service.get_open_rework_cycles()

        assert len(results) == 0
