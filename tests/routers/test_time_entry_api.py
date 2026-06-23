from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from unittest.mock import patch, MagicMock

from app.dependencies import require_permission
from app.services.time_entry_service import TimeEntryService
from tests.conftest import (
    TEST_EMPLOYEE_ID,
    TEST_TASK_ID,
    TEST_TIME_ENTRY_ID,
    make_mock_time_entry,
)

# ==========================================
# LIST
# ==========================================


class TestListTimeEntries:
    async def test_returns_time_entries(self, async_client):
        with patch.object(TimeEntryService, "get_all") as mock_get_all:
            entry = make_mock_time_entry()
            mock_get_all.return_value = ([entry], 1)

            resp = await async_client.get("/api/v1/time-entries", params={"limit": 50})

            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True
            assert len(body["data"]["time_entries"]) == 1
            assert body["data"]["total"] == 1

    async def test_supports_filters(self, async_client):
        with patch.object(TimeEntryService, "get_all") as mock_get_all:
            mock_get_all.return_value = ([], 0)

            resp = await async_client.get(
                "/api/v1/time-entries",
                params={
                    "date_from": "2026-06-01",
                    "date_to": "2026-06-30",
                    "status": "DRAFT",
                    "limit": 10,
                },
            )

            assert resp.status_code == 200
            _, kwargs = mock_get_all.call_args
            assert kwargs.get("status") == "DRAFT"


# ==========================================
# CREATE SINGLE
# ==========================================


class TestCreateTimeEntry:
    async def test_creates_time_entry(self, async_client):
        with patch.object(TimeEntryService, "create") as mock_create:
            entry = make_mock_time_entry()
            mock_create.return_value = entry

            payload = {
                "task_id": str(TEST_TASK_ID),
                "date": "2026-06-15",
                "hours_spent": 4.0,
            }

            resp = await async_client.post("/api/v1/time-entries", json=payload)

            assert resp.status_code == 201
            body = resp.json()
            assert body["success"] is True

    async def test_rejects_invalid_hours(self, async_client):
        payload = {
            "task_id": str(TEST_TASK_ID),
            "date": "2026-06-15",
            "hours_spent": -1,
        }

        resp = await async_client.post("/api/v1/time-entries", json=payload)

        assert resp.status_code == 422

    async def test_rejects_excessive_hours(self, async_client):
        payload = {
            "task_id": str(TEST_TASK_ID),
            "date": "2026-06-15",
            "hours_spent": 25,
        }

        resp = await async_client.post("/api/v1/time-entries", json=payload)

        assert resp.status_code == 422

    async def test_rejects_missing_task(self, async_client):
        payload = {
            "date": "2026-06-15",
            "hours_spent": 4.0,
        }

        resp = await async_client.post("/api/v1/time-entries", json=payload)

        assert resp.status_code == 422


# ==========================================
# BATCH CREATE
# ==========================================


class TestBatchCreateTimeEntries:
    async def test_batch_creates_entries(self, async_client):
        with patch.object(TimeEntryService, "create_batch") as mock_batch:
            entry1 = make_mock_time_entry(hours_spent=2.0)
            entry2 = make_mock_time_entry(
                id=UUID("77777777-7777-4777-8777-777777777777"),
                hours_spent=3.5,
            )
            mock_batch.return_value = [entry1, entry2]

            payload = {
                "entries": [
                    {
                        "task_id": str(TEST_TASK_ID),
                        "date": "2026-06-15",
                        "hours_spent": 2.0,
                    },
                    {
                        "task_id": str(TEST_TASK_ID),
                        "date": "2026-06-16",
                        "hours_spent": 3.5,
                    },
                ]
            }

            resp = await async_client.post("/api/v1/time-entries/batch", json=payload)

            assert resp.status_code == 201
            body = resp.json()
            assert body["success"] is True
            assert len(body["data"]["time_entries"]) == 2

    async def test_batch_rejects_empty_list(self, async_client):
        payload = {"entries": []}

        resp = await async_client.post("/api/v1/time-entries/batch", json=payload)

        assert resp.status_code == 422

    async def test_batch_rejects_invalid_entry(self, async_client):
        payload = {
            "entries": [
                {"task_id": str(TEST_TASK_ID), "date": "2026-06-15", "hours_spent": -1}
            ]
        }

        resp = await async_client.post("/api/v1/time-entries/batch", json=payload)

        assert resp.status_code == 422


# ==========================================
# GET SINGLE
# ==========================================


class TestGetTimeEntry:
    async def test_returns_entry(self, async_client):
        with patch.object(TimeEntryService, "get_by_id") as mock_get:
            entry = make_mock_time_entry(employee_id=TEST_EMPLOYEE_ID)
            mock_get.return_value = entry

            resp = await async_client.get(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}")

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["time_entry"]["id"] == str(TEST_TIME_ENTRY_ID)

    async def test_denies_other_users_entry(self, async_client):
        with patch.object(TimeEntryService, "get_by_id") as mock_get:
            other_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            entry = make_mock_time_entry(id=TEST_TIME_ENTRY_ID, employee_id=other_id)
            mock_get.return_value = entry

            resp = await async_client.get(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}")

            assert resp.status_code == 403

    async def test_returns_404_on_missing(self, async_client):
        with patch.object(TimeEntryService, "get_by_id") as mock_get:
            mock_get.side_effect = ValueError("not found")

            resp = await async_client.get(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}")

            assert resp.status_code == 404


# ==========================================
# UPDATE
# ==========================================


class TestUpdateTimeEntry:
    async def test_updates_draft_entry(self, async_client):
        with patch.object(TimeEntryService, "update") as mock_update:
            entry = make_mock_time_entry(hours_spent=6.0)
            mock_update.return_value = entry

            resp = await async_client.put(
                f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}",
                json={"hours_spent": 6.0},
            )

            assert resp.status_code == 200
            body = resp.json()
            assert body["success"] is True

    async def test_rejects_invalid_data(self, async_client):
        resp = await async_client.put(
            f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}",
            json={"hours_spent": -5},
        )

        assert resp.status_code == 422


# ==========================================
# DELETE
# ==========================================


class TestDeleteTimeEntry:
    async def test_deletes_own_entry(self, async_client):
        with patch.object(TimeEntryService, "delete") as mock_delete:
            mock_delete.return_value = None

            resp = await async_client.delete(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}")

            assert resp.status_code == 200
            assert resp.json()["success"] is True


# ==========================================
# SUBMIT / APPROVE / REJECT
# ==========================================


class TestSubmitTimeEntry:
    async def test_submits(self, async_client):
        with patch.object(TimeEntryService, "submit") as mock_submit:
            entry = make_mock_time_entry(status="SUBMITTED")
            mock_submit.return_value = entry

            resp = await async_client.post(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}/submit")

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["time_entry"]["status"] == "SUBMITTED"


class TestApproveTimeEntry:
    async def test_approves(self, async_client):
        with patch.object(TimeEntryService, "approve") as mock_approve:
            entry = make_mock_time_entry(status="APPROVED")
            mock_approve.return_value = entry

            resp = await async_client.post(f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}/approve")

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["time_entry"]["status"] == "APPROVED"


class TestRejectTimeEntry:
    async def test_rejects_with_reason(self, async_client):
        with patch.object(TimeEntryService, "reject") as mock_reject:
            entry = make_mock_time_entry(status="REJECTED", rejection_reason="Need more info")
            entry.employee_id = TEST_EMPLOYEE_ID
            mock_reject.return_value = entry

            resp = await async_client.post(
                f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}/reject",
                json={"reason": "Need more info"},
            )

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["time_entry"]["status"] == "REJECTED"

    async def test_reject_requires_reason(self, async_client):
        resp = await async_client.post(
            f"/api/v1/time-entries/{TEST_TIME_ENTRY_ID}/reject",
            json={"reason": ""},
        )

        assert resp.status_code == 422


# ==========================================
# MY TIMESHEET SUMMARY
# ==========================================


class TestMyTimesheet:
    async def test_returns_summary(self, async_client):
        with patch.object(TimeEntryService, "get_my_timesheet") as mock_summary:
            from app.schemas.time_entry import TimesheetSummary

            summary = TimesheetSummary(
                employee_id=TEST_EMPLOYEE_ID,
                employee_name="Test User",
                period_start=date(2026, 6, 14),
                period_end=date(2026, 6, 20),
                total_hours=40.0,
                billable_hours=35.0,
                approved_hours=30.0,
                by_project=[],
                by_task=[],
            )
            mock_summary.return_value = summary

            resp = await async_client.get(
                "/api/v1/time-entries/my-timesheet",
                params={"date_from": "2026-06-14", "date_to": "2026-06-20"},
            )

            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["summary"]["total_hours"] == 40.0
