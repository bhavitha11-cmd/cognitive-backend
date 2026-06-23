from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, call
from uuid import UUID

import pytest
from app.models.employee import Employee
from app.models.task import Task
from app.models.project import Project

from tests.conftest import (
    TEST_EMPLOYEE_ID,
    TEST_TASK_ID,
    TEST_PROJECT_ID,
    TEST_OTHER_USER_ID,
    TEST_TIME_ENTRY_ID,
    make_mock_employee,
    make_mock_task,
    make_mock_project,
    make_mock_time_entry,
)

# ==========================================
# CREATE SINGLE
# ==========================================


class TestCreate:
    def test_creates_entry_successfully(self, time_entry_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task()
        mock_proj = make_mock_project()
        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)
        # After commit+refresh, _fetch_entry is called - return a proper mock
        fetched = make_mock_time_entry()
        mock_db.scalars.return_value.unique.return_value.first.return_value = fetched

        from app.schemas.time_entry import TimeEntryCreate

        data = TimeEntryCreate(
            task_id=TEST_TASK_ID,
            date=date(2026, 6, 15),
            hours_spent=4.0,
        )

        result = time_entry_service.create(data)

        assert result is not None
        assert result.hours_spent == 4.0
        assert result.status == "DRAFT"
        assert mock_db.add.called
        assert mock_db.refresh.called

    def test_raises_on_inactive_task(self, time_entry_service, mock_db):
        mock_emp = make_mock_employee()
        mock_task = make_mock_task(is_active=False)
        mock_proj = make_mock_project()
        mock_db.get.side_effect = lambda model, id: {
            Employee: mock_emp if id == TEST_EMPLOYEE_ID else None,
            Task: mock_task if id == TEST_TASK_ID else None,
            Project: mock_proj if id == TEST_PROJECT_ID else None,
        }.get(model)

        from app.schemas.time_entry import TimeEntryCreate

        data = TimeEntryCreate(
            task_id=TEST_TASK_ID,
            date=date(2026, 6, 15),
            hours_spent=4.0,
        )

        with pytest.raises(ValueError, match="inactive task"):
            time_entry_service.create(data)

    def test_raises_when_creating_for_other_user(self, time_entry_service, mock_db):
        from app.schemas.time_entry import TimeEntryCreate

        data = TimeEntryCreate(
            employee_id=TEST_OTHER_USER_ID,
            task_id=TEST_TASK_ID,
            date=date(2026, 6, 15),
            hours_spent=4.0,
        )

        with pytest.raises(ValueError, match="only create time entries for yourself"):
            time_entry_service.create(data)


# ==========================================
# BATCH CREATE
# ==========================================


class TestBatchCreate:
    def test_creates_multiple_entries(self, time_entry_service, mock_db):
        mock_emp = make_mock_employee()
        task_id1 = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        task_id2 = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        mock_task1 = make_mock_task(id=task_id1, task_code="TASK-001")
        mock_task2 = make_mock_task(id=task_id2, task_code="TASK-002")
        mock_proj = make_mock_project()

        added_entries = []

        def mock_get(model, id_val):
            mapping = {
                Employee: mock_emp,
                Task: {task_id1: mock_task1, task_id2: mock_task2}.get(id_val),
                Project: mock_proj,
            }
            return mapping.get(model)

        def mock_add(entry):
            added_entries.append(entry)

        def mock_flush():
            for e in added_entries:
                if e.id is None:
                    e.id = uuid.uuid4()

        # Patch _build_response to avoid relationship access issues
        mock_db.get.side_effect = mock_get
        mock_db.add.side_effect = mock_add
        mock_db.flush.side_effect = mock_flush

        from app.schemas.time_entry import TimeEntryCreate

        data1 = TimeEntryCreate(
            task_id=task_id1,
            date=date(2026, 6, 15),
            hours_spent=2.0,
        )
        data2 = TimeEntryCreate(
            task_id=task_id2,
            date=date(2026, 6, 16),
            hours_spent=3.5,
        )

        results = time_entry_service.create_batch([data1, data2])

        assert len(results) == 2
        assert results[0].hours_spent == 2.0
        assert results[1].hours_spent == 3.5

    def test_raises_if_any_entry_for_other_user(self, time_entry_service, mock_db):
        from app.schemas.time_entry import TimeEntryCreate

        data1 = TimeEntryCreate(
            employee_id=TEST_OTHER_USER_ID,
            task_id=TEST_TASK_ID,
            date=date(2026, 6, 15),
            hours_spent=1.0,
        )
        data2 = TimeEntryCreate(
            task_id=TEST_TASK_ID,
            date=date(2026, 6, 16),
            hours_spent=2.0,
        )

        with pytest.raises(ValueError, match="only create time entries for yourself"):
            time_entry_service.create_batch([data1, data2])

    def test_raises_if_no_current_user(self, mock_db):
        from app.services.time_entry_service import TimeEntryService

        service = TimeEntryService(db=mock_db, current_user_id=None)
        with pytest.raises(ValueError, match="Current user is not set"):
            service.create_batch([])


# ==========================================
# UPDATE
# ==========================================


class TestUpdate:
    def test_updates_draft_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="DRAFT")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        from app.schemas.time_entry import TimeEntryUpdate

        data = TimeEntryUpdate(hours_spent=6.0)
        result = time_entry_service.update(TEST_TIME_ENTRY_ID, data)

        assert result.hours_spent == 6.0
        assert mock_db.commit.called

    def test_raises_on_non_draft_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="SUBMITTED")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        from app.schemas.time_entry import TimeEntryUpdate

        data = TimeEntryUpdate(hours_spent=6.0)
        with pytest.raises(ValueError, match="Only DRAFT entries can be updated"):
            time_entry_service.update(TEST_TIME_ENTRY_ID, data)


# ==========================================
# DELETE
# ==========================================


class TestDelete:
    def test_deletes_draft_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="DRAFT")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        time_entry_service.delete(TEST_TIME_ENTRY_ID)

        mock_db.delete.assert_called_once_with(existing_entry)
        assert mock_db.commit.called

    def test_raises_on_approved_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="APPROVED")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        with pytest.raises(ValueError, match="Only DRAFT or REJECTED entries can be deleted"):
            time_entry_service.delete(TEST_TIME_ENTRY_ID)


# ==========================================
# SUBMIT / APPROVE / REJECT
# ==========================================


class TestSubmit:
    def test_submits_draft_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="DRAFT")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        result = time_entry_service.submit(TEST_TIME_ENTRY_ID)

        assert result.status == "SUBMITTED"
        assert result.submitted_at is not None
        assert mock_db.commit.called

    def test_raises_on_already_submitted(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="SUBMITTED")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        with pytest.raises(ValueError, match="Only DRAFT entries can be submitted"):
            time_entry_service.submit(TEST_TIME_ENTRY_ID)


class TestApprove:
    def test_approves_submitted_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="SUBMITTED")
        existing_entry.approver = None
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        result = time_entry_service.approve(TEST_TIME_ENTRY_ID, TEST_EMPLOYEE_ID)

        assert result.status == "APPROVED"
        assert mock_db.commit.called

    def test_raises_on_draft_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="DRAFT")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        with pytest.raises(ValueError, match="Only SUBMITTED entries can be approved"):
            time_entry_service.approve(TEST_TIME_ENTRY_ID, TEST_EMPLOYEE_ID)


class TestReject:
    def test_rejects_submitted_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="SUBMITTED")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        result = time_entry_service.reject(TEST_TIME_ENTRY_ID, "Need more details", TEST_EMPLOYEE_ID)

        assert result.status == "REJECTED"
        assert result.rejection_reason == "Need more details"
        assert mock_db.commit.called

    def test_rejects_approved_entry(self, time_entry_service, mock_db):
        existing_entry = make_mock_time_entry(status="APPROVED")
        mock_db.scalars.return_value.unique.return_value.first.return_value = existing_entry

        result = time_entry_service.reject(TEST_TIME_ENTRY_ID, "Client dispute", TEST_EMPLOYEE_ID)

        assert result.status == "REJECTED"
        assert mock_db.commit.called


# ==========================================
# GET / LIST / SUMMARY
# ==========================================


class TestList:
    def test_returns_filtered_entries(self, time_entry_service, mock_db):
        entry1 = make_mock_time_entry(date_val=date(2026, 6, 15))
        entry2 = make_mock_time_entry(date_val=date(2026, 6, 16))
        mock_db.scalars.return_value.unique.return_value.all.return_value = [entry1, entry2]
        mock_db.scalar.return_value = 2

        results, total = time_entry_service.get_all(skip=0, limit=50)

        assert total == 2
        assert len(results) == 2

    def test_respects_skip_limit(self, time_entry_service, mock_db):
        mock_db.scalars.return_value.unique.return_value.all.return_value = []
        mock_db.scalar.return_value = 0

        results, total = time_entry_service.get_all(skip=100, limit=10)

        assert total == 0
        assert len(results) == 0

    def test_get_by_id_returns_entry(self, time_entry_service, mock_db):
        entry = make_mock_time_entry()
        mock_db.scalars.return_value.unique.return_value.first.return_value = entry

        result = time_entry_service.get_by_id(TEST_TIME_ENTRY_ID)

        assert result.id == TEST_TIME_ENTRY_ID
        assert result.hours_spent == 4.0

    def test_get_by_id_raises_on_not_found(self, time_entry_service, mock_db):
        mock_db.scalars.return_value.unique.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            time_entry_service.get_by_id(TEST_TIME_ENTRY_ID)


class TestSummary:
    def test_returns_summary_with_breakdowns(self, time_entry_service, mock_db):
        mock_emp = make_mock_employee()
        mock_db.get.return_value = mock_emp

        entry1 = make_mock_time_entry(hours_spent=4.0, is_billable=True, status="APPROVED")
        entry2 = make_mock_time_entry(hours_spent=2.0, is_billable=False, status="DRAFT")
        mock_db.scalars.return_value.unique.return_value.all.return_value = [entry1, entry2]

        summary = time_entry_service.get_timesheet_summary(
            TEST_EMPLOYEE_ID, date(2026, 6, 14), date(2026, 6, 16)
        )

        assert summary.total_hours == 6.0
        assert summary.billable_hours == 4.0
        assert summary.approved_hours == 4.0
        assert len(summary.by_project) == 1
        assert len(summary.by_task) == 1
