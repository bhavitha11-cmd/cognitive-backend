from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from app.services.holiday_service import HolidayService


@pytest.mark.asyncio
async def test_get_emergency_holiday_impact(async_client):
    holiday_id = uuid.uuid4()
    with patch.object(HolidayService, "get_impact_analysis") as mock_impact:
        mock_impact.return_value = {
            "holiday_id": str(holiday_id),
            "holiday_name": "Emergency Storm",
            "holiday_date": "2026-07-01",
            "affected_projects": [],
            "affected_tasks": []
        }

        resp = await async_client.get(f"/api/v1/holidays/emergency/{holiday_id}/impact-analysis")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["holiday_name"] == "Emergency Storm"


@pytest.mark.asyncio
async def test_apply_emergency_holiday(async_client):
    holiday_id = uuid.uuid4()
    with patch.object(HolidayService, "apply_emergency_holiday") as mock_apply:
        mock_apply.return_value = {
            "success": True,
            "message": "Emergency holiday shifts applied successfully"
        }

        payload = {
            "project_updates": [],
            "task_updates": []
        }

        resp = await async_client.post(
            f"/api/v1/holidays/emergency/{holiday_id}/apply",
            json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "applied" in body["message"].lower()


@pytest.mark.asyncio
async def test_reject_emergency_holiday(async_client):
    holiday_id = uuid.uuid4()
    with patch.object(HolidayService, "reject_emergency_holiday") as mock_reject:
        mock_reject.return_value = {
            "success": True,
            "message": "Emergency holiday proposed shifts rejected"
        }

        resp = await async_client.post(f"/api/v1/holidays/emergency/{holiday_id}/reject")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "rejected" in body["message"].lower()
