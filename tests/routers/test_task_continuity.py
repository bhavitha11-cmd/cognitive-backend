from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch, ANY
import pytest

from app.services.task_continuity_service import TaskContinuityService
from app.services.dashboard_widget_service import DashboardWidgetService


@pytest.mark.asyncio
async def test_list_task_risks(async_client):
    from app.repositories.task_continuity_repository import TaskContinuityRepository
    with patch.object(TaskContinuityRepository, "get_all_risks") as mock_get_all:
        risk = MagicMock()
        risk.id = uuid.uuid4()
        risk.task_id = uuid.uuid4()
        risk.task = MagicMock(title="CAM Programming", task_code="TASK-001")
        risk.project_id = uuid.uuid4()
        risk.project = MagicMock(name="Aerospace Project")
        risk.assignment_id = uuid.uuid4()
        risk.employee_id = uuid.uuid4()
        risk.employee = MagicMock(first_name="Ravi", last_name="Kumar")
        risk.leave_request_id = uuid.uuid4()
        risk.leave_start_date = date(2026, 7, 5)
        risk.leave_end_date = date(2026, 7, 10)
        risk.remaining_hours = 28.0
        risk.risk_level = "HIGH"
        risk.days_impacted = 5
        risk.project_impact = "High impact"
        risk.status = "PENDING_MANAGER_ACTION"
        risk.created_at = datetime.now(timezone.utc)
        risk.updated_at = datetime.now(timezone.utc)

        mock_get_all.return_value = [risk]

        resp = await async_client.get("/api/v1/task-continuity/risks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["risks"]) == 1
        assert body["data"]["risks"][0]["task_title"] == "CAM Programming"
        assert body["data"]["risks"][0]["employee_name"] == "Ravi Kumar"


@pytest.mark.asyncio
async def test_resolve_task_risk(async_client):
    with patch.object(TaskContinuityService, "resolve_task_risk") as mock_resolve:
        decision = MagicMock()
        decision.id = uuid.uuid4()
        decision.task_risk_id = uuid.uuid4()
        decision.task_id = uuid.uuid4()
        decision.manager_id = uuid.uuid4()
        decision.decision = "PAUSE"
        decision.details = {"reason": "Pause task until return"}
        decision.decided_at = datetime.now(timezone.utc)

        mock_resolve.return_value = decision

        risk_id = uuid.uuid4()
        payload = {
            "decision": "PAUSE",
            "reason": "Pause task until return",
            "pause_classification": "Leave",
        }

        resp = await async_client.post(
            f"/api/v1/task-continuity/risks/{risk_id}/resolve", json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["decision"]["decision"] == "PAUSE"


@pytest.mark.asyncio
async def test_resume_delegated_task(async_client):
    with patch.object(TaskContinuityService, "resume_delegated_task") as mock_resume:
        delegation_id = uuid.uuid4()
        resp = await async_client.post(
            f"/api/v1/task-continuity/delegations/{delegation_id}/resume"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        mock_resume.assert_called_once_with(delegation_id, ANY)


@pytest.mark.asyncio
async def test_resume_paused_task(async_client):
    with patch.object(TaskContinuityService, "resume_paused_task") as mock_resume:
        task_id = uuid.uuid4()
        resp = await async_client.post(
            f"/api/v1/task-continuity/tasks/{task_id}/resume"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        mock_resume.assert_called_once_with(task_id, ANY)


@pytest.mark.asyncio
async def test_get_tasks_requiring_reassignment(async_client):
    with patch.object(
        DashboardWidgetService, "get_tasks_requiring_reassignment"
    ) as mock_widget:
        mock_widget.return_value = [
            {
                "project_id": str(uuid.uuid4()),
                "project_name": "Aerospace project",
                "task_id": str(uuid.uuid4()),
                "task_code": "TASK-001",
                "task_title": "CAM Programming",
                "employee_id": str(uuid.uuid4()),
                "employee_name": "Ravi Kumar",
                "remaining_hours": 28.0,
                "days_remaining": 5,
                "leave_duration": 6.0,
                "suggested_impact": "High risk",
            }
        ]

        resp = await async_client.get("/api/v1/task-continuity/dashboard/reassignments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]["tasks"]) == 1
        assert body["data"]["tasks"][0]["task_title"] == "CAM Programming"


@pytest.mark.asyncio
async def test_get_continuity_dashboard_kpis(async_client):
    with patch.object(
        DashboardWidgetService, "get_continuity_dashboard_kpis"
    ) as mock_kpis:
        mock_kpis.return_value = {
            "employees_on_leave_with_active_tasks": 2,
            "tasks_at_risk": 5,
            "projects_at_risk": 1,
            "upcoming_resource_shortage": 1,
            "available_engineers_count": 8,
            "overloaded_engineers_count": 1,
            "resource_utilization_pct": 78.5,
            "reassignment_trend": {"2026-06": 4},
        }

        resp = await async_client.get("/api/v1/task-continuity/dashboard/kpis")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["employees_on_leave_with_active_tasks"] == 2
        assert body["data"]["resource_utilization_pct"] == 78.5
        assert body["data"]["reassignment_trend"]["2026-06"] == 4
